"""
The oncology dataset: 5,000 synthetic cancer patients in the Synthea CSV format.

Source: data/synthea/oncology_5k.zip (committed to git) or the same files unzipped in
data/synthea/cancer/. Every patient has one primary cancer (breast, prostate, lung, colon,
melanoma, CLL, non-Hodgkin lymphoma, pancreas) with a TNM stage; see the README inside the zip.

`prepare()` turns the source into the fixed dataset the pipeline reads (data/synthea/current/),
as of AS_OF, and repairs what the generator got wrong:
  * records dated after AS_OF are dropped (the generator scheduled visits up to 2032);
  * encounters after the patient's death are dropped, with everything recorded at them;
  * end dates after AS_OF are cleared (still ongoing on that day);
  * physiologically impossible lab values (negative counts, a percentage over 100) are dropped.
Every repair is counted in data/metadata/oncology_dataset.json. Nothing is invented or re-dated.

    python -m src.ingestion.oncology_dataset          # prepare data/synthea/current/
"""

import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import DATA_DIR, METADATA_DIR, SYNTHEA_CSV_DIR  # noqa: E402
from src.utils.logging_utils import get_logger  # noqa: E402

logger = get_logger("oncology_dataset")

SOURCE_DIR = DATA_DIR / "synthea" / "cancer"
SOURCE_ZIP = DATA_DIR / "synthea" / "oncology_5k.zip"
CURRENT_DIR = SYNTHEA_CSV_DIR
META = METADATA_DIR / "oncology_dataset.json"

AS_OF = "2026-10-16"  # the day the dataset was generated: the platform's "today" for this data

# file -> (date column that says when the row happened, end-date columns cleared if after AS_OF)
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
    "procedures": ("START", ["STOP"]),
    "supplies": ("DATE", []),
    "patients": (None, ["DEATHDATE"]),
    "payer_transitions": (None, []),
    "organizations": (None, []),
    "providers": (None, []),
    "payers": (None, []),
}
# Lab results that can never be negative are all of them here; percentages cannot exceed 100
PERCENT_TESTS = ("Lymphocytes %", "Hematocrit")


def _day(col: str) -> str:
    """Date part of a Synthea date or timestamp column."""
    return f"TRY_CAST(left(\"{col}\", 10) AS DATE)"


def _source(tmp: Path) -> Path:
    """Folder holding the source CSVs: data/synthea/cancer if present, else the zip extracted into `tmp`."""
    if (SOURCE_DIR / "patients.csv").exists():
        return SOURCE_DIR
    if not SOURCE_ZIP.exists():
        raise FileNotFoundError(f"Oncology dataset not found: expected {SOURCE_ZIP} (or its CSVs in {SOURCE_DIR}).")
    with zipfile.ZipFile(SOURCE_ZIP) as z:
        for member in z.namelist():
            if member.endswith(".csv"):
                (tmp / Path(member).name).write_bytes(z.read(member))
    return tmp


def prepare(as_of: str = AS_OF) -> Dict:
    """Write the cleaned dataset as of `as_of` to data/synthea/current/ and record every repair."""
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    fixes: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="oncology_src_") as tmp:
        src = _source(Path(tmp))
        con = duckdb.connect()
        con.execute("SET enable_progress_bar=false")
        read = lambda name: f"read_csv('{(src / f'{name}.csv').as_posix()}', all_varchar=true, header=true)"  # noqa: E731
        cutoff = f"DATE '{as_of}'"

        con.execute(f"CREATE TABLE pat AS SELECT Id, TRY_CAST(DEATHDATE AS DATE) AS death FROM {read('patients')}")
        # Encounters that cannot exist yet (after AS_OF) or after the patient died
        con.execute(f"""
            CREATE TABLE dropped_enc AS
            SELECT e.Id, {_day('START')} > {cutoff} AS future,
                   p.death IS NOT NULL AND {_day('START')} > p.death AS after_death
            FROM {read('encounters')} e JOIN pat p ON p.Id = e.PATIENT
            WHERE {_day('START')} > {cutoff} OR (p.death IS NOT NULL AND {_day('START')} > p.death)
        """)
        fixes["encounters_after_as_of_dropped"] = con.execute("SELECT count(*) FROM dropped_enc WHERE future").fetchone()[0]
        fixes["encounters_after_death_dropped"] = con.execute("SELECT count(*) FROM dropped_enc WHERE NOT future AND after_death").fetchone()[0]

        for name, (event_col, end_cols) in TABLES.items():
            if not (src / f"{name}.csv").exists():
                continue
            cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {read(name)}").fetchall()]
            select = [f"CASE WHEN {_day(c)} > {cutoff} THEN NULL ELSE \"{c}\" END AS \"{c}\"" if c in end_cols else f'"{c}"'
                      for c in cols]
            where = []
            if "ENCOUNTER" in cols:
                where.append("(ENCOUNTER IS NULL OR ENCOUNTER NOT IN (SELECT Id FROM dropped_enc))")
            if name == "encounters":
                where.append("Id NOT IN (SELECT Id FROM dropped_enc)")
            if event_col:
                where.append(f"({_day(event_col)} IS NULL OR {_day(event_col)} <= {cutoff})")
                if "PATIENT" in cols:
                    where.append(f"NOT EXISTS (SELECT 1 FROM pat p WHERE p.Id = PATIENT AND p.death IS NOT NULL AND {_day(event_col)} > p.death)")
            if name == "observations":
                pct = ", ".join(f"'{t}'" for t in PERCENT_TESTS)
                bad = (f"(TRY_CAST(VALUE AS DOUBLE) < 0 OR (DESCRIPTION IN ({pct}) AND TRY_CAST(VALUE AS DOUBLE) > 100))")
                fixes["impossible_lab_values_dropped"] = con.execute(
                    f"SELECT count(*) FROM {read(name)} WHERE {bad}").fetchone()[0]
                where.append(f"NOT coalesce({bad}, false)")
            sql = f"SELECT {', '.join(select)} FROM {read(name)}" + (f" WHERE {' AND '.join(where)}" if where else "")
            before = con.execute(f"SELECT count(*) FROM {read(name)}").fetchone()[0]
            out = (CURRENT_DIR / f"{name}.csv").as_posix()
            con.execute(f"COPY ({sql}) TO '{out}' (HEADER, DELIMITER ',')")
            counts[name] = con.execute(f"SELECT count(*) FROM read_csv('{out}', all_varchar=true, header=true)").fetchone()[0]
            if before != counts[name]:
                fixes[f"{name}_rows_removed"] = before - counts[name]
        con.close()

    meta = {
        "dataset": "Synthetic oncology EHR (Synthea CSV format)",
        "source": (SOURCE_ZIP if not (SOURCE_DIR / "patients.csv").exists() else SOURCE_DIR).relative_to(DATA_DIR.parent).as_posix(),
        "as_of": as_of,
        "rows": counts,
        "repairs": fixes,
        "known_limitations": [
            "Every inpatient stay is a short surgical admission and no patient is admitted twice: no readmissions, length of stay not meaningful.",
            "Emergency visits occur only in the last weeks before death, so they are not used as model features.",
            "Lab values are drawn independently of treatment (no post-chemotherapy dip), so no toxicity model is trained.",
            "Medication costs and dispense counts are near-uniform across drugs.",
            "Most diagnoses that the generator dated after its own cut-off sit on 1-10 Sep 2026 (362 vs about 25 in a normal month), so recent-diagnosis and awaiting-treatment counts are inflated.",
        ],
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
    }
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info(f"Oncology dataset prepared as of {as_of}: {counts.get('patients', 0)} patients; repairs {fixes}")
    return meta


def status() -> Dict:
    return json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
