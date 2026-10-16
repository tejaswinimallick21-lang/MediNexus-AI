"""
Package the runtime state git does not carry (database, models, data, accounts) for a server.

    python deploy/pack_data.py                 # writes medinexus_data.tar.gz in the project root

Stop the app first (DuckDB allows one writer). The archive skips what the server can rebuild or
does not need: the original CSVs (the server unzips the Synthea download instead), the pre-re-date
database backup, legacy raw files and sandbox uploads. Copy it to the server with scp and pass it to
deploy/setup_server.sh --data.
"""

import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "medinexus_data.tar.gz"

INCLUDE = [
    "database/healthcare.duckdb",
    "backend/seed_users.json",
    "models",
    "data/synthea/current",
    "data/raw",
    "data/bronze",
    "data/silver",
    "data/gold",
    "data/ops",
    "data/rag",
    "data/metadata",
]


def database_in_use() -> bool:
    import urllib.request

    import duckdb

    # The API opens the database only per request, so also check whether it is running at all
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/system/status", timeout=2)
        return True
    except OSError:
        pass
    try:
        duckdb.connect(str(ROOT / "database" / "healthcare.duckdb")).close()
        return False
    except duckdb.IOException:
        return True


def main() -> int:
    missing = [p for p in INCLUDE if not (ROOT / p).exists()]
    if missing:
        print("Missing (run scripts/bootstrap.py first):\n  " + "\n  ".join(missing))
        return 1
    if database_in_use():
        print("The database is in use. Stop the app (npm run dev / the API) and run this again.")
        return 1
    print(f"Writing {OUT.name} ...", flush=True)
    with tarfile.open(OUT, "w:gz", compresslevel=6) as tar:
        for p in INCLUDE:
            print(f"  + {p}", flush=True)
            tar.add(ROOT / p, arcname=p)
    print(f"Done: {OUT} ({OUT.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
