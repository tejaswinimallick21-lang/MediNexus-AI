"""
Bronze → Silver cleaning for an uploaded table, with a step-by-step report of every change.

Policy: fix what is unambiguous (types, whitespace, casing variants, exact duplicates, impossible
values), pseudonymise personal identifiers, and *report* missing values rather than silently
filling them; models impute inside their own training folds.
"""

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

MAX_ROWS = 500_000
DROP_MISSING_SHARE = 0.95  # columns this empty carry no information

ColumnKind = str  # numeric | datetime | boolean | category | text | identifier

_BOOL_VALUES = {"true": True, "false": False, "yes": True, "no": False, "y": True, "n": False, "t": True, "f": False}
_PII_NAME = re.compile(
    r"(^|_)(first|last|middle|maiden|full|given|family|sur)?_?name($|_)|^(first|last|middle|maiden|surname|prefix_name)$|ssn|social_security|passport"
    r"|^drivers?$|drivers?_?licen|phone|mobile|email|e_mail|address|street|zip|postcode", re.I)
_GEO_NAME = re.compile(r"^(lat|lon|lng|latitude|longitude)$", re.I)
_BIRTH_NAME = re.compile(r"birth_?date|^dob$|date_of_birth", re.I)
_SSN = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_PHONE = re.compile(r"^\+?[\d\s().-]{10,16}$")
_ID_NAME = re.compile(r"(^|_)(id|uuid|guid|key|mrn|code)$", re.I)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_CODE_NAME = re.compile(r"(^|_)(code|icd|snomed|cpt|loinc|rxnorm|ndc)($|_)", re.I)
_DATE_NAME = re.compile(r"date|time|_at$|_on$|dob|birth|start|stop|end", re.I)


@dataclass
class CleaningResult:
    df: pd.DataFrame
    steps: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    quality: Dict[str, float] = field(default_factory=dict)
    rows_in: int = 0
    rows_out: int = 0


def read_table(raw: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV / Parquet / JSON (array or JSON-lines). Raises ValueError with a readable message."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext not in ("csv", "parquet", "json", "jsonl", "ndjson"):
        raise ValueError("Upload a .csv, .parquet or .json file.")
    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(raw), low_memory=False, nrows=MAX_ROWS + 1)
        elif ext == "parquet":
            df = pd.read_parquet(io.BytesIO(raw))
        else:
            text = raw.decode("utf-8-sig")
            if text.lstrip().startswith("["):
                df = pd.json_normalize(json.loads(text))
            else:
                df = pd.read_json(io.StringIO(text), lines=True)
    except Exception as e:  # parser errors are reported to the user, not raised as 500s
        raise ValueError(f"Could not read the file as {ext.upper()}: {e}") from e
    if df.empty or len(df.columns) == 0:
        raise ValueError("The file has no rows or no columns.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"The sandbox accepts up to {MAX_ROWS:,} rows per file.")
    return df


def _snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).strip("_").lower()
    return s or "column"


def _normalise_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    seen: Dict[str, int] = {}
    new = []
    for c in df.columns:
        base = _snake(c)
        n = seen.get(base, 0)
        seen[base] = n + 1
        new.append(base if n == 0 else f"{base}_{n + 1}")
    renamed = sum(1 for a, b in zip(df.columns, new) if str(a) != b)
    out = df.copy()
    out.columns = new
    return out, renamed


def _infer_kind(name: str, s: pd.Series) -> Tuple[ColumnKind, pd.Series, int]:
    """Returns (kind, converted series, values that could not be converted)."""
    non_null = s.dropna()
    if non_null.empty:
        return "text", s, 0
    if pd.api.types.is_bool_dtype(s):
        return "boolean", s, 0
    if pd.api.types.is_numeric_dtype(s):
        if _CODE_NAME.search(name):
            return "category", s.astype("Int64").astype("string") if np.allclose(non_null % 1, 0) else s.astype("string"), 0
        kind = "identifier" if _ID_NAME.search(name) and non_null.nunique() > 0.95 * len(non_null) else "numeric"
        return kind, s, 0
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", s, 0

    as_str = non_null.astype(str).str.strip()
    if as_str.head(1000).str.match(_UUID).mean() > 0.9:
        return "identifier", s, 0  # keys that link to other tables, even when they repeat
    lowered = as_str.str.lower()
    if lowered.isin(_BOOL_VALUES.keys()).mean() >= 0.98 and lowered.nunique() <= 2:
        return "boolean", s.map(lambda v: _BOOL_VALUES.get(str(v).strip().lower()) if pd.notna(v) else None).astype("boolean"), 0

    numeric = pd.to_numeric(as_str.str.replace(r"[,$%\s]", "", regex=True), errors="coerce")
    if numeric.notna().mean() >= 0.95:
        full = pd.to_numeric(s.astype(str).str.replace(r"[,$%\s]", "", regex=True), errors="coerce").where(s.notna())
        if _ID_NAME.search(name) and numeric.nunique() > 0.95 * len(numeric):
            return "identifier", s, 0
        return "numeric", full, int(numeric.isna().sum())

    if _DATE_NAME.search(name) or as_str.str.match(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}").mean() > 0.8:
        dates = pd.to_datetime(as_str, errors="coerce", utc=True, format="mixed")
        if dates.notna().mean() >= 0.9:
            full = pd.to_datetime(s.where(s.notna()).astype("string"), errors="coerce", utc=True, format="mixed").dt.tz_localize(None)
            return "datetime", full, int(dates.isna().sum())

    unique_share = as_str.nunique() / len(as_str)
    if unique_share > 0.95 and (_ID_NAME.search(name) or as_str.str.len().median() >= 8):
        return "identifier", s, 0
    if as_str.nunique() <= max(50, int(0.05 * len(as_str))) or (_CODE_NAME.search(name) and unique_share < 0.5):
        return "category", s, 0
    return "text", s, 0


def _standardise_categories(s: pd.Series) -> Tuple[pd.Series, int]:
    """Map spelling variants that differ only by case/spacing to their most frequent form."""
    non_null = s.dropna().astype(str)
    key = non_null.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    canonical = non_null.groupby(key).agg(lambda v: v.value_counts().index[0])
    mapped = s.map(lambda v: canonical.get(re.sub(r"\s+", " ", str(v).strip().lower()), v) if pd.notna(v) else v)
    changed = int((mapped.dropna().astype(str) != s.dropna().astype(str)).sum())
    return mapped, changed


_ORG = re.compile(
    r"hospital|clinic|cent(?:er|re)|medical|health|pharma|insurance|assurance|medicare|medicaid|shield|cross|mutual|"
    r"(?:inc|ltd|llc|corp|plc|co|plan|payer|group|trust|foundation|university|labs?|care|national|united)", re.I)


def _is_pii(name: str, s: pd.Series) -> bool:
    if _PII_NAME.search(name):
        # A bare "name" column of organisations (hospitals, payers) is not personal data
        if re.fullmatch(r"(full_)?name", name):
            sample = s.dropna().astype(str).head(500)
            if not sample.empty and sample.str.contains(_ORG).mean() > 0.3:
                return False
        return True
    sample = s.dropna().astype(str).str.strip().head(500)
    if sample.empty:
        return False
    return bool(sample.str.match(_SSN).mean() > 0.5 or sample.str.match(_EMAIL).mean() > 0.5 or
                (sample.str.match(_PHONE).mean() > 0.8 and sample.str.contains(r"[\s().-]").mean() > 0.5))


def _pseudonymise(s: pd.Series, salt: str) -> pd.Series:
    """Stable per-upload tokens: the same person maps to the same token, so joins and counts still work."""
    return s.map(lambda v: "PII_" + hashlib.sha256(f"{salt}|{v}".encode()).hexdigest()[:10] if pd.notna(v) else v)


def clean(df: pd.DataFrame, salt: str) -> CleaningResult:
    res = CleaningResult(df=df, rows_in=len(df))
    total_cells = max(1, df.size)

    df, renamed = _normalise_columns(df)
    res.steps.append({"step": "Standardise column names", "detail": "snake_case, unique names", "affected": renamed})

    trimmed = 0
    for c in df.columns:
        if df[c].dtype == object:
            s = df[c]
            stripped = s.where(~s.map(lambda v: isinstance(v, str)), s.astype("string").str.strip())
            stripped = stripped.replace({"": np.nan, "NA": np.nan, "N/A": np.nan, "null": np.nan, "NULL": np.nan, "None": np.nan, "nan": np.nan})
            trimmed += int((stripped.astype("string").fillna("<NA>") != s.astype("string").fillna("<NA>")).sum())
            df[c] = stripped
    res.steps.append({"step": "Trim whitespace and blank markers", "detail": "'', NA, N/A, null → missing", "affected": trimmed})

    kinds: Dict[str, ColumnKind] = {}
    failed = 0
    for c in df.columns:
        kind, converted, bad = _infer_kind(c, df[c])
        kinds[c] = kind
        df[c] = converted
        failed += bad
    res.steps.append({"step": "Infer and convert data types", "detail": "numbers, dates, booleans, categories, identifiers",
                      "affected": failed, "note": "values that could not be converted are set to missing"})

    standardised = 0
    for c, k in kinds.items():
        if k == "category":
            df[c], n = _standardise_categories(df[c])
            standardised += n
    res.steps.append({"step": "Standardise category spellings", "detail": "case and spacing variants merged", "affected": standardised})

    invalid = 0
    today = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    for c, k in kinds.items():
        if k == "numeric" and re.search(r"(^|_)age($|_)", c):
            bad = (df[c] < 0) | (df[c] > 120)
            invalid += int(bad.sum())
            df.loc[bad, c] = np.nan
        elif k == "datetime":
            bad = df[c] > today
            if re.search(r"birth|dob", c):
                bad |= df[c] < pd.Timestamp("1900-01-01")
            invalid += int(bad.sum())
            df.loc[bad, c] = pd.NaT
    res.steps.append({"step": "Remove impossible values", "detail": "ages outside 0–120, dates in the future", "affected": invalid})

    pii_cols = [c for c, k in kinds.items() if k in ("text", "category", "identifier", "numeric") and not _GEO_NAME.match(c) and _is_pii(c, df[c])]
    for c in pii_cols:
        df[c] = _pseudonymise(df[c], salt)
        kinds[c] = "identifier"
    res.steps.append({"step": "Pseudonymise personal identifiers", "detail": ", ".join(pii_cols) or "none detected", "affected": len(pii_cols)})

    # Quasi-identifiers are generalised rather than removed so they stay useful for analysis
    generalised = []
    for c, k in list(kinds.items()):
        if k == "numeric" and _GEO_NAME.match(c):
            df[c] = df[c].round(1)  # ~11 km
            generalised.append(f"{c} → 1 decimal (~11 km)")
        elif k == "datetime" and _BIRTH_NAME.search(c):
            year = f"{c}_year"
            df[year] = df[c].dt.year.astype("Int64")
            df = df.drop(columns=[c])
            kinds.pop(c)
            kinds[year] = "numeric"
            generalised.append(f"{c} → {year}")
    res.steps.append({"step": "Generalise quasi-identifiers", "detail": "; ".join(generalised) or "none detected", "affected": len(generalised)})

    before = len(df)
    hashable = df.astype("string")
    df = df.loc[~hashable.duplicated()].reset_index(drop=True)
    dupes = before - len(df)
    res.steps.append({"step": "Remove exact duplicate rows", "detail": "identical across every column", "affected": dupes})

    # Quality is scored on the file as received (after type fixes), before empty columns are dropped
    missing_received = int(df.isna().sum().sum())
    cells_received = max(1, df.size)
    empty_cols = [c for c in df.columns if df[c].isna().mean() >= DROP_MISSING_SHARE]
    if empty_cols:
        df = df.drop(columns=empty_cols)
        for c in empty_cols:
            kinds.pop(c, None)
    res.steps.append({"step": "Drop near-empty columns", "detail": ", ".join(empty_cols) or f"none ≥{int(DROP_MISSING_SHARE * 100)}% missing", "affected": len(empty_cols)})

    missing_cells = int(df.isna().sum().sum())
    res.steps.append({"step": "Report missing values", "detail": "left as missing; models impute inside their training folds", "affected": missing_cells})

    res.df = df
    res.rows_out = len(df)
    for c in df.columns:
        s = df[c]
        res.columns.append({
            "name": c, "kind": kinds[c], "missing_pct": round(float(s.isna().mean() * 100), 2),
            "unique": int(s.nunique(dropna=True)), "pii_masked": c in pii_cols,
            "example": None if s.dropna().empty else str(s.dropna().iloc[0])[:60],
        })

    completeness = 1 - missing_received / cells_received
    validity = 1 - (failed + invalid) / total_cells
    uniqueness = 1 - dupes / max(1, before)
    consistency = 1 - standardised / total_cells
    res.quality = {
        "completeness": round(completeness * 100, 1), "validity": round(validity * 100, 1),
        "uniqueness": round(uniqueness * 100, 1), "consistency": round(consistency * 100, 1),
        "overall": round((0.4 * completeness + 0.3 * validity + 0.2 * uniqueness + 0.1 * consistency) * 100, 1),
    }
    return res
