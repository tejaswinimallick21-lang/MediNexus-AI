"""
Create the .gitignored seed file (backend/seed_users.json) from the committed template.

    python -m backend.scripts.create_seed_users                     # dev password from MEDINEXUS_SEED_PASSWORD or the README demo default
    python -m backend.scripts.create_seed_users --password '...'    # one password for every seeded user
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.security import hash_password  # noqa: E402

TEMPLATE = PROJECT_ROOT / "backend" / "seed_users.example.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "backend" / "seed_users.json"
DEV_DEFAULT_PASSWORD = "MediNexus@2026"  # documented demo password (README); override for anything shared


def build_seed(password: str, template: Path = TEMPLATE) -> dict:
    users = json.loads(template.read_text(encoding="utf-8"))["users"]
    return {"users": [{**u, "password_hash": hash_password(password)} for u in users]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", default=os.getenv("MEDINEXUS_SEED_PASSWORD", DEV_DEFAULT_PASSWORD))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing seed file")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        sys.exit(f"{args.output} already exists (use --force to overwrite).")
    seed = build_seed(args.password)
    args.output.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    print(f"Wrote {len(seed['users'])} users to {args.output}")


if __name__ == "__main__":
    main()
