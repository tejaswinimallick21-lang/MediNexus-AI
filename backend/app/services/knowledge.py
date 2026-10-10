"""
Knowledge library management for the Nexa agents' policy search (admin only).

Library documents live in documents/ (version-controlled); documents added here go to
data/knowledge/ (gitignored). The hybrid index rebuilds itself when files change; embeddings are
cached per chunk, so only new or edited text is embedded.
"""

import re
from typing import Any, Dict

from fastapi import UploadFile

from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from backend.app.schemas.security import KnowledgeDoc, KnowledgeLibrary, SearchComparison, SearchHit
from src.rag import benchmark
from src.rag.hybrid import IDENTIFIER, UPLOADED_DIR, get_index
from src.security.audit import log_audit_event

MAX_BYTES = 1024 * 1024


def library() -> KnowledgeLibrary:
    idx = get_index()
    docs: Dict[str, Dict[str, Any]] = {}
    for c in idx.chunks:
        d = docs.setdefault(c.doc_id, {"doc_id": c.doc_id, "title": c.title, "policy_id": c.policy_id, "category": c.category,
                                       "filename": c.filename, "source": c.source, "sections": set(), "words": 0})
        d["sections"].add(c.section)
        d["words"] += len(c.text.split())
    out = [KnowledgeDoc(**{**d, "sections": len(d["sections"])}) for d in docs.values()]
    out.sort(key=lambda d: (d.source != "uploaded", d.category, d.title))
    return KnowledgeLibrary(documents=out, chunks=len(idx.chunks), dense_model=idx.dense_label, dense_error=idx.dense_error)


async def upload(file: UploadFile, user: UserRecord) -> KnowledgeLibrary:
    name = (file.filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem, _, ext = name.rpartition(".")
    if ext.lower() not in ("txt", "md") or not stem:
        raise APIError(422, "unsupported_file", "Upload a .txt or .md document.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise APIError(413, "file_too_large", "Documents up to 1 MB are accepted.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise APIError(422, "not_utf8", "The document must be UTF-8 text.")
    if len(text.split()) < 20:
        raise APIError(422, "too_short", "The document is too short to be useful (fewer than 20 words).")
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")[:60] or "document"
    if any(c.doc_id == slug and c.source == "library" for c in get_index().chunks):
        raise APIError(409, "name_taken", f"A library document is already called '{slug}'. Rename the file.")
    UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOADED_DIR / f"{slug}.{ext.lower()}").write_text(text, encoding="utf-8")
    log_audit_event(username=user.email, role=user.role, action="KNOWLEDGE_UPLOAD", resource=slug, status="SUCCESS", details=f"{name} ({len(data):,} bytes)")
    return library()


def delete(doc_id: str, user: UserRecord) -> None:
    if not re.fullmatch(r"[a-z0-9_]{1,60}", doc_id):
        raise APIError(404, "document_not_found", "No such uploaded document.")
    files = [p for p in UPLOADED_DIR.glob(f"{doc_id}.*")] if UPLOADED_DIR.exists() else []
    if not files:
        raise APIError(404, "document_not_found", "Only documents uploaded here can be deleted; library documents are managed in version control.")
    for p in files:
        p.unlink()
    log_audit_event(username=user.email, role=user.role, action="KNOWLEDGE_DELETE", resource=doc_id, status="SUCCESS", details="Removed from the knowledge library")


def compare(query: str, k: int) -> SearchComparison:
    idx = get_index()
    results = {mode: [SearchHit(**{f: h.as_dict()[f] for f in SearchHit.model_fields}) for h in idx.search(query, k=k, mode=mode)]
               for mode in ("bm25", "dense", "hybrid")}
    return SearchComparison(query=query, identifier_query=bool(IDENTIFIER.search(query)), dense_model=idx.dense_label, results=results)


def benchmark_results(run: bool = False) -> Dict[str, Any]:
    if run:
        return benchmark.run_benchmark()
    return benchmark.last_results() or benchmark.run_benchmark()
