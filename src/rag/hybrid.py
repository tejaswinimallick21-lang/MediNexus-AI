"""
Hybrid retrieval for the MediNexus knowledge library.

    lexical  BM25 over section-aware chunks: exact terms, policy codes, numbers ("POL-LAB-001", "2-8°C")
    dense    embeddings: meaning, so "how cold must insulin be kept" finds "Refrigerated medications 2°C to 8°C"
             - OpenAI text-embedding-3-small when an OpenAI key is configured (cached on disk per chunk)
             - otherwise a local latent-semantic model (TF-IDF + SVD); weaker, but free and offline
    fusion   query-adaptive score blending (normalised scores): mostly meaning by default, mostly keywords
             when the question contains an identifier or a figure with a unit (policy codes, "70 g/L").
             Chosen over Reciprocal Rank Fusion because the benchmark showed rank fusion letting keyword
             noise outvote correct meaning matches on everyday-language questions.
    abstain  no result when neither method finds anything relevant, so out-of-scope questions are refused

Chunks follow the documents' numbered sections, so every hit can be cited as "document · section".
"""

import hashlib
import json
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config.constants import DATA_DIR, DOCUMENTS_DIR

UPLOADED_DIR = DATA_DIR / "knowledge"  # documents added by administrators (gitignored)
CACHE_DIR = DATA_DIR / "rag"
EMBED_MODEL = os.getenv("NEXA_EMBED_MODEL", "text-embedding-3-small")
DENSE_WEIGHT = {"openai": 0.85, "local": 0.4}  # share of the blend given to meaning (non-identifier questions)
EXACT_DENSE_WEIGHT = 0.25  # identifier / figure questions lean on keywords
BM25_STRONG = 8.0  # a keyword match this strong counts as relevant even if meaning search disagrees
# Policy codes (POL-IT-002, CPG-CLIN-009) and figures with units (70 g/L, 4 mmol/L, 48 hours)
IDENTIFIER = re.compile(r"\b[A-Z]{2,}-[A-Z]{2,}-\d{2,4}\b|\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|mmol|ml|l|%|°c|mmhg|hours?|days?|minutes?)(?=[^a-z]|$)", re.I)
MAX_SECTION_WORDS = 220
# Abstention thresholds (calibrated with the benchmark's out-of-scope suite)
BM25_MIN = float(os.getenv("NEXA_RAG_BM25_MIN", "2.5"))
DENSE_MIN = {"openai": float(os.getenv("NEXA_RAG_DENSE_MIN", "0.38")), "local": 0.35}

STOP = set("""a an and are as at be by can could do does for from had has have how i if in into is it its may me must my of on or our should
so than that the their them then there these they this to under up was we were what when where which who why will with within without you your
about after all also any before being both each other per such until upon very would""".split())


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ities", "ings", "ing", "ies", "ied", "ers", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
    return w


def tokenize(text: str) -> List[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    filename: str
    title: str
    policy_id: str
    category: str
    section: str
    text: str
    source: str  # library | uploaded

    @property
    def search_text(self) -> str:
        return f"{self.title} ({self.policy_id}). {self.section}. {self.text}" if self.policy_id else f"{self.title}. {self.section}. {self.text}"


# ---- loading & chunking ---------------------------------------------------------------------------

def _meta(content: str, fallback_title: str) -> Tuple[str, str, str]:
    title, pid = fallback_title, ""
    for line in content.splitlines()[:8]:
        if "DOCUMENT TITLE:" in line:
            title = line.split("DOCUMENT TITLE:", 1)[1].strip()
        elif "DOCUMENT ID:" in line:
            pid = line.split("DOCUMENT ID:", 1)[1].strip()
    body = "\n".join(l for l in content.splitlines() if not re.match(r"\s*(\[DEMO|DOCUMENT TITLE:|DOCUMENT ID:|REVISION:|EFFECTIVE DATE:)", l))
    return title, pid, body.strip()


def chunk_text(doc_id: str, filename: str, category: str, content: str, source: str) -> List[Chunk]:
    title, pid, body = _meta(content, Path(filename).stem.replace("_", " ").title())
    # Split on numbered or markdown headings; text before the first heading is an "Overview"
    parts = re.split(r"\n(?=\s*(?:\d+\.\s+[A-Z][A-Z0-9 ,&/()\-]{3,}|#{1,3}\s+\S))", "\n" + body)
    chunks: List[Chunk] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first, _, rest = part.partition("\n")
        is_heading = bool(re.match(r"(\d+\.\s+[A-Z]|#{1,3}\s)", first))
        section = re.sub(r"^(\d+\.|#{1,3})\s*", "", first).strip().title() if is_heading else "Overview"
        text = (rest if is_heading else part).strip() or first
        words = text.split()
        step = MAX_SECTION_WORDS - 40
        for i in range(0, max(1, len(words)), step):  # long sections: overlapping windows
            piece = " ".join(words[i: i + MAX_SECTION_WORDS])
            if piece:
                chunks.append(Chunk(f"{doc_id}#{len(chunks)}", doc_id, filename, title, pid, category, section, piece, source))
            if i + MAX_SECTION_WORDS >= len(words):
                break
    return chunks


def load_chunks() -> List[Chunk]:
    chunks: List[Chunk] = []
    for base, source in ((DOCUMENTS_DIR, "library"), (UPLOADED_DIR, "uploaded")):
        if not base.exists():
            continue
        for p in sorted(base.glob("**/*")):
            if p.suffix.lower() in (".txt", ".md") and p.is_file():
                category = "Uploaded" if source == "uploaded" else p.parent.name.replace("_", " ").title()
                chunks += chunk_text(p.stem, p.name, category, p.read_text(encoding="utf-8", errors="replace"), source)
    return chunks


# ---- lexical: BM25 --------------------------------------------------------------------------------

class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=float)
        self.avg = float(self.len.mean()) if len(docs) else 0.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: List[str]) -> np.ndarray:
        out = np.zeros(len(self.tf))
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return out


# ---- dense: embeddings ----------------------------------------------------------------------------

def _norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(n == 0, 1, n)


class OpenAIEmbedder:
    kind = "openai"

    def __init__(self) -> None:
        import openai

        self.client = openai.OpenAI()
        self.path = CACHE_DIR / f"embeddings_{EMBED_MODEL}.json"
        self.cache: Dict[str, List[float]] = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.label = f"OpenAI {EMBED_MODEL}"

    def _embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 96):
            resp = self.client.embeddings.create(model=EMBED_MODEL, input=texts[i: i + 96])
            out += [d.embedding for d in resp.data]
        return out

    def fit(self, texts: List[str]) -> np.ndarray:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in self.cache]
        if missing:  # only new or changed chunks cost anything
            for (k, _), v in zip(missing, self._embed([t for _, t in missing])):
                self.cache[k] = v
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache))
        return _norm(np.array([self.cache[k] for k in keys], dtype=float))

    def query(self, text: str) -> np.ndarray:
        return _norm(np.array(self._embed([text])[0], dtype=float))


class LocalEmbedder:
    """Latent semantic analysis: captures co-occurring vocabulary, not true meaning. Free and offline."""

    kind = "local"
    label = "Local LSA (TF-IDF + SVD)"

    def fit(self, texts: List[str]) -> np.ndarray:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(tokenizer=tokenize, lowercase=False, ngram_range=(1, 2), sublinear_tf=True, token_pattern=None)
        x = self.vec.fit_transform(texts)
        self.svd = TruncatedSVD(n_components=max(2, min(96, x.shape[0] - 1, x.shape[1] - 1)), random_state=7)
        return _norm(self.svd.fit_transform(x))

    def query(self, text: str) -> np.ndarray:
        return _norm(self.svd.transform(self.vec.transform([text]))[0])


def make_embedder(prefer: Optional[str] = None):
    choice = (prefer or os.getenv("NEXA_EMBEDDINGS", "")).lower()
    try:
        from backend.app.agents import providers  # loads the project .env  # noqa: F401
    except Exception:
        pass
    if choice != "local" and os.getenv("OPENAI_API_KEY") and os.getenv("NEXA_LLM_PROVIDER", "") != "rules":
        try:
            return OpenAIEmbedder()
        except Exception:
            pass
    return LocalEmbedder()


# ---- index ----------------------------------------------------------------------------------------

@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25: float
    dense: float
    bm25_rank: Optional[int]
    dense_rank: Optional[int]

    def as_dict(self) -> Dict[str, Any]:
        c = self.chunk
        return {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "title": c.title, "policy_id": c.policy_id, "filename": c.filename,
                "category": c.category, "section": c.section, "source": c.source, "text": c.text, "score": round(self.score, 4),
                "bm25": round(self.bm25, 3), "dense": round(self.dense, 3), "bm25_rank": self.bm25_rank, "dense_rank": self.dense_rank}


@dataclass
class HybridIndex:
    chunks: List[Chunk] = field(default_factory=list)
    embedder: Any = None
    dense_error: Optional[str] = None

    def build(self, prefer: Optional[str] = None) -> "HybridIndex":
        self.chunks = load_chunks()
        texts = [c.search_text for c in self.chunks]
        self.bm25 = BM25([tokenize(t) for t in texts])
        self.embedder = make_embedder(prefer)
        try:
            self.vectors = self.embedder.fit(texts) if texts else np.zeros((0, 2))
        except Exception as e:  # e.g. API unreachable: fall back to the local model
            self.dense_error = f"{type(e).__name__}"
            self.embedder = LocalEmbedder()
            self.vectors = self.embedder.fit(texts) if texts else np.zeros((0, 2))
        return self

    @property
    def dense_label(self) -> str:
        return self.embedder.label if self.embedder else "none"

    def search(self, query: str, k: int = 3, mode: str = "hybrid", abstain: bool = True) -> List[Hit]:
        if not self.chunks or not query.strip():
            return []
        bm = self.bm25.scores(tokenize(query))
        try:
            dn = self.vectors @ self.embedder.query(query)
        except Exception:
            dn = np.zeros(len(self.chunks))
            mode = "bm25" if mode != "bm25" else mode
        bm_order = [i for i in np.argsort(-bm) if bm[i] > 0]
        dn_order = list(np.argsort(-dn))
        bm_rank = {i: r + 1 for r, i in enumerate(bm_order)}
        dn_rank = {i: r + 1 for r, i in enumerate(dn_order)}
        exact = bool(IDENTIFIER.search(query))
        if abstain:
            dense_ok = dn.max() >= DENSE_MIN.get(self.embedder.kind, 0.35)
            lexical_ok = bm.max() >= (BM25_MIN if exact else BM25_STRONG)
            if mode == "bm25" and not bm.max() >= BM25_MIN or mode == "dense" and not dense_ok or mode == "hybrid" and not (dense_ok or lexical_ok):
                return []
        if mode == "bm25":
            order, score = bm_order, {i: float(bm[i]) for i in bm_order}
        elif mode == "dense":
            order, score = dn_order, {i: float(dn[i]) for i in dn_order}
        else:
            w = EXACT_DENSE_WEIGHT if exact else DENSE_WEIGHT.get(self.embedder.kind, 0.5)
            bn = bm / bm.max() if bm.max() > 0 else bm
            dnn = (dn - dn.min()) / (dn.max() - dn.min() + 1e-9)
            blend = w * dnn + (1 - w) * bn
            order = list(np.argsort(-blend))
            score = {i: float(blend[i]) for i in order}
        hits, seen_sections = [], set()
        for i in order:
            key = (self.chunks[i].doc_id, self.chunks[i].section)
            if key in seen_sections:  # one hit per section (overlapping windows)
                continue
            seen_sections.add(key)
            hits.append(Hit(self.chunks[i], score[i], float(bm[i]), float(dn[i]), bm_rank.get(i), dn_rank.get(i)))
            if len(hits) >= k:
                break
        return hits


_index: Optional[HybridIndex] = None
_lock = threading.Lock()


def _signature() -> str:
    files = [p for base in (DOCUMENTS_DIR, UPLOADED_DIR) if base.exists() for p in base.glob("**/*") if p.is_file()]
    return "|".join(f"{p}:{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in sorted(files))


_sig = ""


def get_index(force: bool = False) -> HybridIndex:
    """Shared index, rebuilt automatically when library files change."""
    global _index, _sig
    with _lock:
        sig = _signature()
        if force or _index is None or sig != _sig:
            _index = HybridIndex().build()
            _sig = sig
        return _index
