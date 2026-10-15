"""
Rebuild everything git does not carry (data, database, models, accounts) on a fresh machine.

    python scripts/bootstrap.py            # run every step that is still missing
    python scripts/bootstrap.py --force    # re-run every step

Prerequisite: the Synthea COVID-19 10K CSV export extracted into data/synthea/csv/
(https://synthetichealth.github.io/synthea/downloads.html -> 10k_synthea_covid19_csv.zip).
The first two steps re-date it to today and drop the 2020 COVID-19 period (src/ingestion/redate_synthea.py).
Each step is the same command documented in docs/SETUP.md, run in order.
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def table_exists(name: str) -> bool:
    db = ROOT / "database" / "healthcare.duckdb"
    if not db.exists():
        return False
    import duckdb

    con = duckdb.connect(str(db), read_only=True)
    try:
        return bool(con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0])
    finally:
        con.close()


def models_trained() -> bool:
    return table_exists("model_registry") and len(list((ROOT / "models").glob("*.joblib"))) >= 6


STEPS = [
    ("Re-date Synthea to today (records up to 2019, COVID-19 period removed)", [sys.executable, "-m", "src.ingestion.redate_synthea", "redate"],
     lambda: (ROOT / "data" / "metadata" / "synthea_redate.json").exists()),
    ("Release re-dated records up to now", [sys.executable, "-m", "src.ingestion.redate_synthea", "release"],
     lambda: (ROOT / "data" / "synthea" / "current" / "patients.csv").exists()),
    ("Convert Synthea CSVs into raw tables", [sys.executable, "-m", "src.ingestion.synthea_adapter"], lambda: any((ROOT / "data" / "raw").glob("*.csv"))),
    ("Run the Medallion pipeline (Bronze -> Silver -> Gold)", [sys.executable, "-m", "src.medallion.pipeline"], lambda: table_exists("gold_admissions")),
    ("Generate simulated operations data", [sys.executable, "-m", "src.ingestion.ops_simulator", "--years", "3", "--seed", "7"], lambda: table_exists("sim_outpatient_daily_all")),
    ("Train and register the ML models", [sys.executable, "-m", "src.ml.train_demand"], models_trained),
    ("Create the three sign-in accounts", [sys.executable, "-m", "backend.scripts.create_seed_users"], lambda: (ROOT / "backend" / "seed_users.json").exists()),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Re-run steps that already look complete")
    args = parser.parse_args()

    csv_dir = ROOT / "data" / "synthea" / "csv"
    if not (csv_dir / "patients.csv").exists():
        print(f"Missing Synthea data: extract 10k_synthea_covid19_csv.zip into {csv_dir}\n"
              "Download: https://synthetichealth.github.io/synthea/downloads.html")
        return 1
    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
        print("Created .env from .env.example - add your OPENAI_API_KEY (or ANTHROPIC_API_KEY) to it.")

    for title, cmd, done in STEPS:
        if done() and not args.force:
            print(f"[skip] {title} (already done)")
            continue
        print(f"[run ] {title} ...", flush=True)
        started = time.time()
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            print(f"[fail] {title}. Fix the error above, then run this script again (finished steps are skipped).")
            return 1
        print(f"[ ok ] {title} ({time.time() - started:.0f}s)")
    print("\nDone. Start the app with:  npm run dev   then open http://localhost:5173")
    return 0


if __name__ == "__main__":
    sys.exit(main())
