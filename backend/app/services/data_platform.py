"""
Data Engineering workspace: the upload sandbox.

Each upload lives in data/uploads/<upload_id>/ (raw file = Bronze, silver.parquet = cleaned,
clean.csv = Gold export, manifest.json = status and every report). Nothing here writes to
data/raw or to the live lakehouse tables; promotion is a separate, approved step.
"""

import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import UploadFile

from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.core.users import UserRecord
from backend.app.jobs import runner
from backend.app.schemas.data_platform import (
    ForecastIn,
    JobAccepted,
    UploadAccepted,
    UploadDetail,
    UploadSummary,
)
from config.constants import DATA_DIR, GOLD_TABLES
from src.sandbox.cleaning import clean, read_table
from src.sandbox.forecast import forecast as run_forecast
from src.sandbox.modeling import predict_column
from src.sandbox.profiling import profile as run_profile
from src.sandbox.summary import summarise
from src.security.audit import log_audit_event
from src.utils.database import query_df_strict

UPLOADS_DIR = Path(os.getenv("MEDINEXUS_UPLOADS_DIR", str(DATA_DIR / "uploads")))
MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {"csv", "parquet", "json", "jsonl", "ndjson"}
PREVIEW_ROWS = 20

_manifest_lock = threading.Lock()


# ---- manifest storage --------------------------------------------------------------------------

def _dir(upload_id: str) -> Path:
    return UPLOADS_DIR / upload_id


def _read(upload_id: str) -> Dict[str, Any]:
    path = _dir(upload_id) / "manifest.json"
    if not path.exists():
        raise APIError(404, "upload_not_found", "No such upload.")
    with _manifest_lock:
        return json.loads(path.read_text(encoding="utf-8"))


def _update(upload_id: str, /, **fields: Any) -> Dict[str, Any]:
    path = _dir(upload_id) / "manifest.json"
    with _manifest_lock:
        m = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        m.update(fields)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, default=_json_default, indent=1), encoding="utf-8")
        tmp.replace(path)
        return m


def _json_default(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    return str(v)


def _summary(m: Dict[str, Any]) -> UploadSummary:
    c = m.get("cleaning") or {}
    return UploadSummary(
        upload_id=m["upload_id"], filename=m["filename"], size_bytes=m["size_bytes"], sha256=m["sha256"], uploaded_by=m["uploaded_by"],
        created_at=m["created_at"], status=m["status"], stage=m.get("stage", ""),
        rows=c.get("rows_out"), columns=len(c.get("columns", [])) or None, quality_score=(c.get("quality") or {}).get("overall"),
    )


def _kinds(m: Dict[str, Any]) -> Dict[str, str]:
    return {c["name"]: c["kind"] for c in (m.get("cleaning") or {}).get("columns", [])}


def _pii(m: Dict[str, Any]) -> List[str]:
    return [c["name"] for c in (m.get("cleaning") or {}).get("columns", []) if c.get("pii_masked")]


def _load_clean(upload_id: str) -> pd.DataFrame:
    path = _dir(upload_id) / "silver.parquet"
    if not path.exists():
        raise APIError(409, "upload_not_ready", "This upload has not finished processing.")
    return pd.read_parquet(path)


def _resummarise(upload_id: str) -> None:
    m = _read(upload_id)
    _update(upload_id, summary=summarise(m))


# ---- lakehouse comparison (read-only) ---------------------------------------------------------

def _gold_columns() -> Dict[str, List[str]]:
    df = query_df_strict(
        f"SELECT table_name, column_name FROM information_schema.columns WHERE table_name IN ({', '.join('?' for _ in GOLD_TABLES)})",
        list(GOLD_TABLES),
    )
    return {t: list(g["column_name"]) for t, g in df.groupby("table_name")}


def _gold_sample(table: str, cols: List[str]) -> pd.DataFrame:
    if table not in GOLD_TABLES:
        raise ValueError("Unknown table")
    select = ", ".join(f'TRY_CAST("{c}" AS DOUBLE) AS "{c}"' for c in cols)
    return query_df_strict(f'SELECT {select} FROM "{table}" USING SAMPLE 20000 ROWS')


# ---- pipeline --------------------------------------------------------------------------------

def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_parquet(path, index=False)
    except (ValueError, TypeError, ArithmeticError):
        safe = df.copy()
        for c in safe.columns:
            if safe[c].dtype == object:
                safe[c] = safe[c].astype("string")
        safe.to_parquet(path, index=False)


def _pipeline_job(upload_id: str, raw_path: Path, filename: str, salt: str):
    def run(ctx: runner.JobContext) -> Dict[str, Any]:
        try:
            ctx.progress(10, "Bronze: reading the raw file")
            _update(upload_id, stage="Bronze: reading the raw file")
            df = read_table(raw_path.read_bytes(), filename)
            ctx.progress(30, f"Silver: cleaning {len(df):,} rows × {df.shape[1]} columns")
            _update(upload_id, stage="Silver: cleaning")
            res = clean(df, salt)
            _write_parquet(res.df, _dir(upload_id) / "silver.parquet")
            ctx.progress(55, "Gold: publishing the analysis-ready table")
            res.df.to_csv(_dir(upload_id) / "clean.csv", index=False)
            cleaning = {"rows_in": res.rows_in, "rows_out": res.rows_out, "steps": res.steps, "columns": res.columns, "quality": res.quality}
            _update(upload_id, stage="Insights: profiling", cleaning=cleaning)
            ctx.progress(70, "Insights: profiling, segments and drift")
            kinds = {c["name"]: c["kind"] for c in res.columns}
            prof = run_profile(res.df, kinds, _gold_columns, _gold_sample)
            _update(upload_id, profile=prof)
            ctx.progress(95, "Writing the summary")
            _update(upload_id, status="ready", stage="Ready", job_id=None)
            _resummarise(upload_id)
            return {"upload_id": upload_id, "rows": res.rows_out}
        except Exception as e:
            _update(upload_id, status="failed", stage="Failed", error=str(e) if isinstance(e, ValueError) else "Processing failed; see the job log.", job_id=None)
            raise
    return run


async def create_upload(file: UploadFile, user: UserRecord) -> UploadAccepted:
    name = Path(file.filename or "").name
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED:
        raise APIError(422, "unsupported_file", "Upload a .csv, .parquet or .json file.")
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise APIError(413, "file_too_large", f"Files up to {MAX_BYTES // (1024 * 1024)} MB are accepted.")
    if not data:
        raise APIError(422, "empty_file", "The file is empty.")

    upload_id = uuid.uuid4().hex
    folder = _dir(upload_id)
    folder.mkdir(parents=True, exist_ok=False)
    raw_path = folder / f"raw.{ext}"
    raw_path.write_bytes(bytes(data))
    manifest = {
        "upload_id": upload_id, "filename": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "uploaded_by": user.email, "created_at": datetime.now().isoformat(timespec="seconds"), "status": "processing",
        "stage": "Queued", "predictions": {}, "forecast": None, "summary": [],
    }
    _update(upload_id, **manifest)
    job = runner.submit("sandbox_pipeline", user.email, _pipeline_job(upload_id, raw_path, name, salt=uuid.uuid4().hex))
    _update(upload_id, job_id=job.job_id)
    log_audit_event(username=user.email, role=user.role, action="SANDBOX_UPLOAD", resource=upload_id, status="SUCCESS",
                    details=f"{name} ({len(data):,} bytes, sha256 {manifest['sha256'][:12]}…)")
    return UploadAccepted(upload=_summary(_read(upload_id)), job_id=job.job_id)


def list_uploads(params: PageParams) -> Page[UploadSummary]:
    if not UPLOADS_DIR.exists():
        return build_page([], params)
    manifests = []
    for p in UPLOADS_DIR.glob("*/manifest.json"):
        try:
            manifests.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    manifests.sort(key=lambda m: (m.get("created_at", ""), m.get("upload_id", "")), reverse=True)
    rows = [_summary(m) for m in manifests[params.offset: params.offset + params.limit + 1]]
    return build_page(rows, params)


def get_upload(upload_id: str) -> UploadDetail:
    m = _read(upload_id)
    cols: List[str] = []
    rows: List[List[Optional[str]]] = []
    if m["status"] == "ready" and (_dir(upload_id) / "silver.parquet").exists():
        head = pd.read_parquet(_dir(upload_id) / "silver.parquet").head(PREVIEW_ROWS)
        cols = [str(c) for c in head.columns]
        rows = [[_cell(v) for v in r] for r in head.itertuples(index=False)]
    return UploadDetail(
        **_summary(m).model_dump(), error=m.get("error"), job_id=m.get("job_id"), cleaning=m.get("cleaning"), profile=m.get("profile"),
        predictions=list((m.get("predictions") or {}).values()), forecast=m.get("forecast"), summary=m.get("summary") or [],
        preview_columns=cols, preview_rows=rows,
    )


def _cell(v: Any) -> Optional[str]:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp) and v == v.normalize():
        return str(v.date())
    return str(v)[:80]


def delete_upload(upload_id: str, user: UserRecord) -> None:
    m = _read(upload_id)
    if m["status"] == "processing":
        raise APIError(409, "upload_busy", "Wait for processing to finish before deleting.")
    shutil.rmtree(_dir(upload_id))
    log_audit_event(username=user.email, role=user.role, action="SANDBOX_DELETE", resource=upload_id, status="SUCCESS", details=m["filename"])


def clean_csv_path(upload_id: str, user: UserRecord) -> Path:
    m = _read(upload_id)
    path = _dir(upload_id) / "clean.csv"
    if m["status"] != "ready" or not path.exists():
        raise APIError(409, "upload_not_ready", "This upload has not finished processing.")
    log_audit_event(username=user.email, role=user.role, action="SANDBOX_DOWNLOAD", resource=upload_id, status="SUCCESS", details=m["filename"])
    return path


def _require_ready(upload_id: str) -> Dict[str, Any]:
    m = _read(upload_id)
    if m["status"] != "ready":
        raise APIError(409, "upload_not_ready", "This upload has not finished processing.")
    if m.get("job_id") and (j := runner.get(m["job_id"])) and j.status in ("queued", "running"):
        raise APIError(409, "upload_busy", "An analysis is already running for this upload.")
    return m


def start_prediction(upload_id: str, target: str, user: UserRecord) -> JobAccepted:
    m = _require_ready(upload_id)
    kinds = _kinds(m)
    if target not in kinds:
        raise APIError(422, "unknown_column", f"'{target}' is not a column of the cleaned table.")
    if kinds[target] in ("identifier", "text", "datetime"):
        raise APIError(422, "invalid_target", f"'{target}' is an identifier, free text or a date; choose a numeric or categorical column.")

    def run(ctx: runner.JobContext) -> Dict[str, Any]:
        try:
            ctx.progress(15, f"Training a model to predict {target}")
            result = predict_column(_load_clean(upload_id), kinds, target, _pii(m))
            ctx.progress(90, "Comparing with the baseline")
            preds = dict(_read(upload_id).get("predictions") or {})
            preds[target] = result
            _update(upload_id, predictions=preds, job_id=None, prediction_error=None)
            _resummarise(upload_id)
            return {"target": target, "beats_baseline": result["beats_baseline"]}
        except Exception as e:
            _update(upload_id, job_id=None, prediction_error=str(e))
            raise

    job = runner.submit("sandbox_predict", user.email, run)
    _update(upload_id, job_id=job.job_id)
    log_audit_event(username=user.email, role=user.role, action="SANDBOX_PREDICT", resource=upload_id, status="SUCCESS", details=f"target={target}")
    return JobAccepted(job_id=job.job_id)


def start_forecast(upload_id: str, body: ForecastIn, user: UserRecord) -> JobAccepted:
    m = _require_ready(upload_id)
    kinds = _kinds(m)
    if kinds.get(body.date_column) != "datetime":
        raise APIError(422, "invalid_date_column", f"'{body.date_column}' is not a date column.")
    if body.value_column and kinds.get(body.value_column) != "numeric":
        raise APIError(422, "invalid_value_column", f"'{body.value_column}' is not a numeric column.")

    def run(ctx: runner.JobContext) -> Dict[str, Any]:
        try:
            ctx.progress(15, "Building the time series")
            result = run_forecast(_load_clean(upload_id), body.date_column, body.value_column, body.aggregation)
            ctx.progress(90, "Backtest complete")
            _update(upload_id, forecast=result, job_id=None, forecast_error=None)
            _resummarise(upload_id)
            return {"serving_method": result["serving_method"]}
        except Exception as e:
            _update(upload_id, job_id=None, forecast_error=str(e))
            raise

    job = runner.submit("sandbox_forecast", user.email, run)
    _update(upload_id, job_id=job.job_id)
    log_audit_event(username=user.email, role=user.role, action="SANDBOX_FORECAST", resource=upload_id, status="SUCCESS",
                    details=f"{body.date_column} / {body.value_column or 'row count'}")
    return JobAccepted(job_id=job.job_id)
