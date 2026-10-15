"""
Live data feed: releases the re-dated Synthea records day by day and rebuilds the lakehouse.

Every night (MEDINEXUS_FEED_TIME, default 01:00) and on demand from Data Engineering:
  1. release the re-dated records dated up to now (src/ingestion/redate_synthea.py);
  2. convert them to raw tables and run Bronze -> Silver -> Gold;
  3. expose the simulated operations days up to now (sim_ tables);
  4. drop cached model scores so the next request scores the new data.
When the held-back events run out, the source is re-anchored to today first (all dates move forward
by whole weeks), so the feed never goes stale. Models are not retrained here; retraining is a
separate step (python -m src.ml.train_demand).

Runs inside the API process because DuckDB allows one writing process. Disabled with
MEDINEXUS_FEED_ENABLED=0 (tests).
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.security.audit import log_audit_event
from src.utils.database import execute_query, query_df_strict

logger = logging.getLogger("medinexus.feed")
FEED_TIME = os.getenv("MEDINEXUS_FEED_TIME", "01:00")
_ready = False


def _ensure() -> None:
    global _ready
    if _ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS data_feed_runs (
            run_id VARCHAR, trigger VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR,
            released_through VARCHAR, held_back_days INTEGER, reanchored BOOLEAN, error VARCHAR
        )
    """)
    _ready = True


def run_refresh(trigger: str = "manual", ctx: Any = None, user: str = "data-feed@medinexus.org") -> Dict[str, Any]:
    """Release up to now, rebuild the lakehouse and refresh the simulated operations window."""
    from datetime import date

    from src.ingestion import convert_synthea_to_raw
    from src.ingestion.ops_simulator import release_sim
    from src.ingestion.redate_synthea import redate, release, status
    from src.medallion.pipeline import run_full_medallion_pipeline

    def step(pct: int, stage: str) -> None:
        if ctx is not None:
            ctx.progress(pct, stage)
        logger.info(f"Data feed: {stage}")

    _ensure()
    run_id, started = uuid.uuid4().hex[:12], datetime.now()
    execute_query("INSERT INTO data_feed_runs (run_id, trigger, started_at, status, reanchored) VALUES (?, ?, ?, 'running', FALSE)",
                  [run_id, trigger, started])
    try:
        meta = status().get("redate") or {}
        reanchored = not meta or date.fromisoformat(meta["redated_end"]) <= date.today()
        if reanchored:
            step(5, "Re-anchoring the source to today")
            redate()
        step(15, "Releasing records dated up to now")
        rel = release()
        step(30, "Converting to raw tables")
        convert_synthea_to_raw()
        step(45, "Running Bronze -> Silver -> Gold")
        run_full_medallion_pipeline(username=user, auto_generate_raw_if_missing=False, retrain_models=False)
        step(90, "Updating simulated operations")
        release_sim()
        from backend.app.services import clinical

        clinical._score_cache.clear()
        execute_query("UPDATE data_feed_runs SET finished_at = ?, status = 'succeeded', released_through = ?, held_back_days = ?, reanchored = ? WHERE run_id = ?",
                      [datetime.now(), rel["released_through"], rel["held_back_days"], reanchored, run_id])
        log_audit_event(username=user, role="system", action="DATA_FEED_REFRESH", resource="lakehouse", status="SUCCESS",
                        details=f"trigger={trigger}; released through {rel['released_through']}; re-anchored={reanchored}")
        return {"run_id": run_id, "released_through": rel["released_through"], "held_back_days": rel["held_back_days"], "reanchored": reanchored}
    except Exception as e:
        execute_query("UPDATE data_feed_runs SET finished_at = ?, status = 'failed', error = ? WHERE run_id = ?", [datetime.now(), str(e)[:500], run_id])
        log_audit_event(username=user, role="system", action="DATA_FEED_REFRESH", resource="lakehouse", status="FAILED", details=str(e)[:200])
        raise


def recent_runs(limit: int = 5) -> List[Dict[str, Any]]:
    _ensure()
    df = query_df_strict("SELECT * FROM data_feed_runs ORDER BY started_at DESC LIMIT ?", [limit])
    out = []
    for r in df.to_dict("records"):
        out.append({k: (None if v != v else (v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else v)) for k, v in r.items()})
    return out


def next_run_at(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    hh, mm = (int(x) for x in FEED_TIME.split(":"))
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt.isoformat(timespec="minutes")


def feed_status() -> Dict[str, Any]:
    from src.ingestion.redate_synthea import status

    meta = status()
    runs = recent_runs()
    return {
        "enabled": os.getenv("MEDINEXUS_FEED_ENABLED", "1") != "0",
        "redate": meta.get("redate"),
        "release": meta.get("release"),
        "runs": runs,
        "next_run_at": next_run_at(),
    }


def _ran_today() -> bool:
    _ensure()
    df = query_df_strict("SELECT count(*) AS n FROM data_feed_runs WHERE CAST(started_at AS DATE) = current_date AND trigger = 'schedule'")
    return int(df.iloc[0]["n"]) > 0


def start_scheduler(stop: threading.Event) -> Optional[threading.Thread]:
    """Nightly refresh in a background thread (submitted to the single job runner)."""
    if os.getenv("MEDINEXUS_FEED_ENABLED", "1") == "0":
        return None

    def loop() -> None:
        from backend.app.jobs import runner

        while not stop.wait(60):
            try:
                hh, mm = (int(x) for x in FEED_TIME.split(":"))
                now = datetime.now()
                due = now.hour > hh or (now.hour == hh and now.minute >= mm)
                if due and not _ran_today() and runner.active_job("data_feed") is None:
                    runner.submit("data_feed", "data-feed@medinexus.org", lambda ctx: run_refresh("schedule", ctx))
            except Exception as e:  # never let the scheduler thread die
                logger.warning(f"Data feed scheduler check failed: {e}")
                time.sleep(5)

    t = threading.Thread(target=loop, name="data-feed-scheduler", daemon=True)
    t.start()
    return t
