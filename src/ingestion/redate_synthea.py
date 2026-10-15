"""
Re-date the Synthea export so the platform runs on current dates, without the COVID-19 period.

The downloaded export (Synthea COVID-19 10K) runs to May 2020, and from 20 Jan 2020 it is dominated
by the COVID-19 module. Two steps turn it into a present-day dataset:

1. redate (once, or to re-anchor): keep every record that starts on or before 31 Dec 2019 (so no
   COVID-19 at all), then move every date forward by the same whole number of weeks so the data ends
   about HORIZON_DAYS after today. Birth dates move too, so ages and every patient's history stay
   consistent; weekdays are preserved. Output: data/synthea/redated/.
2. release (daily): copy the re-dated records up to "now" into data/synthea/current/, which the
   pipeline reads. Records dated later are held back and released as their time arrives, so the
   dashboards move forward day by day ("live replay"). Ongoing conditions, medications and deaths
   dated after now are cleared, exactly as they would look on that day.

Nothing is invented: these are the same Synthea patients and events, re-dated. Metadata is written
to data/metadata/synthea_redate.json and synthea_release.json.

    python -m src.ingestion.redate_synthea redate      # re-anchor to today (+ HORIZON_DAYS of held-back events)
    python -m src.ingestion.redate_synthea release     # release everything dated up to now
"""

import argparse
import json
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import DATA_DIR, METADATA_DIR, SYNTHEA_CSV_DIR, SYNTHEA_SOURCE_DIR  # noqa: E402
from src.utils.logging_utils import get_logger  # noqa: E402

logger = get_logger("redate_synthea")

SOURCE_DIR = SYNTHEA_SOURCE_DIR                    # the original download, unzipped (optional: the zip is enough)
SOURCE_ZIP = DATA_DIR / "synthea" / "10k_synthea_covid19_csv.zip"  # the original download as published
REDATED_DIR = DATA_DIR / "synthea" / "redated"     # cut + shifted, including held-back future events
CURRENT_DIR = SYNTHEA_CSV_DIR                      # what the pipeline reads: released up to now
REDATE_META = METADATA_DIR / "synthea_redate.json"
RELEASE_META = METADATA_DIR / "synthea_release.json"

ORIGINAL_CUTOFF = "2019-12-31 23:59:59"  # last moment before the COVID-19 module starts (first case 20 Jan 2020)
HORIZON_DAYS = 30                        # held-back events released day by day after a redate

# file -> (event column that decides whether a row exists yet, other date columns cleared if after the cut)
TABLES: Dict[str, tuple] = {
    "allergies": ("START", ["STOP"]),
    "careplans": ("START", ["STOP"]),
    "conditions": ("START", ["STOP"]),
    "devices": ("START", ["STOP"]),
    "encounters": ("START", ["STOP"]),
    "imaging_studies": ("DATE", []),
    "immunizations": ("DATE", []),
    "medications": ("START", ["STOP"]),
    "observations": ("DATE", []),
    "procedures": ("DATE", []),
    "supplies": ("DATE", []),
    "patients": ("BIRTHDATE", ["DEATHDATE"]),
    "payer_transitions": (None, []),   # years only: shifted, not cut
    "organizations": (None, []),
    "providers": (None, []),
    "payers": (None, []),
}
DATE_COLUMNS = {"START", "STOP", "DATE", "BIRTHDATE", "DEATHDATE"}


def _ts(col: str) -> str:
    """A Synthea date ('2019-08-01') or timestamp ('2019-02-16T01:02:32Z') as a TIMESTAMP, ignoring the zone."""
    return f"TRY_CAST(replace(replace(\"{col}\", 'T', ' '), 'Z', '') AS TIMESTAMP)"


def _shifted(col: str, days: int) -> str:
    """Shift a date column by whole days, keeping its original text format."""
    if days == 0:
        return f'"{col}"'
    return (f"CASE WHEN \"{col}\" IS NULL OR \"{col}\" = '' THEN \"{col}\" "
            f"WHEN length(\"{col}\") = 10 THEN strftime(CAST(\"{col}\" AS DATE) + INTERVAL {days} DAY, '%Y-%m-%d') "
            f"ELSE strftime({_ts(col)} + INTERVAL {days} DAY, '%Y-%m-%dT%H:%M:%SZ') END")


def _transform(src: Path, dst: Path, cutoff: str, shift_days: int, shift_years: int) -> Dict[str, int]:
    """Keep rows whose event date is on or before `cutoff`, clear later end dates, then shift all dates."""
    dst.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    counts = {}
    for name, (event_col, end_cols) in TABLES.items():
        path = src / f"{name}.csv"
        if not path.exists():
            continue
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_csv('{path.as_posix()}', all_varchar=true, header=true)").fetchall()]
        select = []
        for c in cols:
            if c in end_cols:  # an end date after the cut is not known yet: still ongoing / alive
                expr = f"CASE WHEN {_ts(c)} > TIMESTAMP '{cutoff}' THEN NULL ELSE \"{c}\" END"
                select.append(f"{_shifted_expr(expr, c, shift_days)} AS \"{c}\"")
            elif c in DATE_COLUMNS:
                select.append(f"{_shifted(c, shift_days)} AS \"{c}\"")
            elif name == "payer_transitions" and c in ("START_YEAR", "END_YEAR") and shift_years:
                select.append(f"CAST(TRY_CAST(\"{c}\" AS INTEGER) + {shift_years} AS VARCHAR) AS \"{c}\"")
            else:
                select.append(f'"{c}"')
        where = f"WHERE {_ts(event_col)} <= TIMESTAMP '{cutoff}'" if event_col else ""
        out = (dst / f"{name}.csv").as_posix()
        con.execute(f"COPY (SELECT {', '.join(select)} FROM read_csv('{path.as_posix()}', all_varchar=true, header=true) {where}) "
                    f"TO '{out}' (HEADER, DELIMITER ',')")
        counts[name] = con.execute(f"SELECT count(*) FROM read_csv('{out}', all_varchar=true, header=true)").fetchone()[0]
    con.close()
    return counts


def _shifted_expr(expr: str, col: str, days: int) -> str:
    """Shift an already-cleared date expression (same rules as _shifted)."""
    if days == 0:
        return expr
    return (f"CASE WHEN ({expr}) IS NULL OR ({expr}) = '' THEN ({expr}) "
            f"WHEN length({expr}) = 10 THEN strftime(CAST(({expr}) AS DATE) + INTERVAL {days} DAY, '%Y-%m-%d') "
            f"ELSE strftime(TRY_CAST(replace(replace(({expr}), 'T', ' '), 'Z', '') AS TIMESTAMP) + INTERVAL {days} DAY, '%Y-%m-%dT%H:%M:%SZ') END")


def _source_csvs(tmp: Path) -> Path:
    """Folder holding the original CSVs: data/synthea/csv if present, else the zip extracted into `tmp`."""
    if (SOURCE_DIR / "patients.csv").exists():
        return SOURCE_DIR
    if not SOURCE_ZIP.exists():
        raise FileNotFoundError(f"Synthea source not found: put {SOURCE_ZIP.name} in {SOURCE_ZIP.parent} (or its CSVs in {SOURCE_DIR}).")
    with zipfile.ZipFile(SOURCE_ZIP) as z:
        for member in z.namelist():
            if member.endswith(".csv"):
                (tmp / Path(member).name).write_bytes(z.read(member))
    return tmp


def redate(today: Optional[date] = None, horizon_days: int = HORIZON_DAYS) -> Dict:
    """Cut the source at 31 Dec 2019 and shift it so it ends about `horizon_days` after today."""
    today = today or date.today()
    original_end = datetime.fromisoformat(ORIGINAL_CUTOFF).date()
    target_end = today + timedelta(days=horizon_days)
    shift_days = ((target_end - original_end).days // 7) * 7  # whole weeks: weekday patterns stay intact
    shift_years = round(shift_days / 365.25)
    logger.info(f"Re-dating Synthea: cut at {ORIGINAL_CUTOFF}, shift {shift_days} days (~{shift_years} years)")
    with tempfile.TemporaryDirectory(prefix="synthea_src_") as tmp:
        src = _source_csvs(Path(tmp))
        counts = _transform(src, REDATED_DIR, ORIGINAL_CUTOFF, shift_days, shift_years)
    meta = {
        "source": str(SOURCE_DIR if src == SOURCE_DIR else SOURCE_ZIP), "original_cutoff": ORIGINAL_CUTOFF, "shift_days": shift_days, "shift_years": shift_years,
        "redated_end": str(original_end + timedelta(days=shift_days)), "anchored_on": str(today),
        "rows": counts, "covid_period_removed": "records after 2019-12-31 in the original data (COVID-19 starts 2020-01-20)",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    REDATE_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def release(as_of: Optional[datetime] = None) -> Dict:
    """Copy re-dated records dated up to `as_of` (default: now) into the folder the pipeline reads."""
    if not REDATE_META.exists():
        raise FileNotFoundError("Run `python -m src.ingestion.redate_synthea redate` first.")
    as_of = (as_of or datetime.now()).replace(microsecond=0)
    counts = _transform(REDATED_DIR, CURRENT_DIR, as_of.strftime("%Y-%m-%d %H:%M:%S"), 0, 0)
    redate_meta = json.loads(REDATE_META.read_text(encoding="utf-8"))
    held_back = max(0, (date.fromisoformat(redate_meta["redated_end"]) - as_of.date()).days)
    meta = {"released_through": as_of.isoformat(), "held_back_days": held_back, "rows": counts,
            "released_at": datetime.now().isoformat(timespec="seconds")}
    RELEASE_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info(f"Released Synthea records through {as_of} ({held_back} days still held back)")
    return meta


def status() -> Dict:
    out = {}
    for key, path in (("redate", REDATE_META), ("release", RELEASE_META)):
        out[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["redate", "release", "status"])
    parser.add_argument("--horizon", type=int, default=HORIZON_DAYS, help="days of events held back after today (redate)")
    args = parser.parse_args()
    if args.step == "redate":
        print(json.dumps(redate(horizon_days=args.horizon), indent=2))
    elif args.step == "release":
        print(json.dumps(release(), indent=2))
    else:
        print(json.dumps(status(), indent=2))
