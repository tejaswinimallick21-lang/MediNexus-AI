"""
User accounts: one per person, stored in DuckDB (table app_users).

The .gitignored seed file (backend/seed_users.json, created with `npm run seed`) bootstraps the
store: any seed account not yet in the table is added on first use, and existing accounts are
never overwritten. After that, administrators manage people in Security & Infrastructure.
"""

import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.access import ROLES
from backend.app.core.config import settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class UserRecord:
    email: str
    name: str
    role: str
    department: str
    password_hash: str
    active: bool = True
    must_change_password: bool = False
    password_changed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    created_by: str = ""
    last_login_at: Optional[datetime] = None
    session_version: int = 0  # bumped on password change, reset or disable: older sessions stop working


class SeedFileError(RuntimeError):
    pass


_seed_lock = threading.Lock()
_seed_cache: Dict[Path, Dict[str, UserRecord]] = {}


def load_users(path: Optional[Path] = None) -> Dict[str, UserRecord]:
    """Parse and validate the seed file once per path; keyed by lower-case email."""
    path = Path(path or settings.seed_file)
    with _seed_lock:
        if path in _seed_cache:
            return _seed_cache[path]
        if not path.exists():
            raise SeedFileError(f"Seed file not found: {path}. Create it with `npm run seed`.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        users: Dict[str, UserRecord] = {}
        for entry in raw.get("users", []):
            email = str(entry["email"]).strip().lower()
            role = entry["role"]
            if not EMAIL_RE.match(email):
                raise SeedFileError(f"Invalid email in seed file: {email}")
            if role not in ROLES:
                raise SeedFileError(f"Unknown role '{role}' for {email}; expected one of {ROLES}")
            users[email] = UserRecord(
                email=email,
                name=entry["name"],
                role=role,
                department=entry.get("department", ""),
                password_hash=entry["password_hash"],
            )
        _seed_cache[path] = users
        return users


# ---- account store (DuckDB) ------------------------------------------------------------------

COLUMNS = ["email", "name", "role", "department", "password_hash", "active", "must_change_password",
           "password_changed_at", "created_at", "created_by", "last_login_at", "session_version"]

_store_lock = threading.RLock()
_store: Optional[Dict[str, UserRecord]] = None
_ready = False


def _ensure() -> None:
    """Create the table and add seed accounts that are not in it yet (never overwrites)."""
    global _ready
    from src.utils.database import execute_query, query_df_strict

    if _ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS app_users (
            email VARCHAR PRIMARY KEY, name VARCHAR, role VARCHAR, department VARCHAR, password_hash VARCHAR,
            active BOOLEAN, must_change_password BOOLEAN, password_changed_at TIMESTAMP,
            created_at TIMESTAMP, created_by VARCHAR, last_login_at TIMESTAMP, session_version INTEGER
        )
    """)
    execute_query("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS session_version INTEGER")
    existing = set(query_df_strict("SELECT email FROM app_users")["email"])
    now = datetime.now()
    for u in load_users().values():
        if u.email not in existing:
            execute_query(f"INSERT INTO app_users ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                          [u.email, u.name, u.role, u.department, u.password_hash, True, False, None, now, "seed file", None, 0])
    _ready = True


def _value(v: Any) -> Any:
    """DuckDB NULLs come back as NaN/NaT through pandas."""
    try:
        import pandas as pd

        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _load() -> Dict[str, UserRecord]:
    global _store
    from src.utils.database import query_df_strict

    with _store_lock:
        if _store is None:
            _ensure()
            df = query_df_strict(f"SELECT {', '.join(COLUMNS)} FROM app_users")
            users = {}
            for r in df.to_dict("records"):
                r = {k: _value(v) for k, v in r.items()}
                r["active"] = bool(r["active"])
                r["must_change_password"] = bool(r["must_change_password"])
                r["created_by"] = r["created_by"] or ""
                r["department"] = r["department"] or ""
                r["session_version"] = int(r["session_version"] or 0)
                for k in ("password_changed_at", "created_at", "last_login_at"):
                    r[k] = r[k].to_pydatetime() if hasattr(r[k], "to_pydatetime") else r[k]
                users[r["email"]] = UserRecord(**r)
            _store = users
        return _store


def get_user(email: str) -> Optional[UserRecord]:
    return _load().get((email or "").strip().lower())


def list_users() -> List[UserRecord]:
    return sorted(_load().values(), key=lambda u: (not u.active, u.role, u.name.lower()))


def insert_user(user: UserRecord) -> None:
    from src.utils.database import execute_query

    with _store_lock:
        _ensure()
        execute_query(f"INSERT INTO app_users ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                      [getattr(user, c) for c in COLUMNS])
        clear_cache()


def update_user(email: str, **fields: Any) -> None:
    from src.utils.database import execute_query

    unknown = set(fields) - set(COLUMNS[1:])
    if unknown:
        raise ValueError(f"Unknown user fields: {sorted(unknown)}")
    with _store_lock:
        _ensure()
        sets = ", ".join(f"{k} = ?" for k in fields)
        execute_query(f"UPDATE app_users SET {sets} WHERE email = ?", [*fields.values(), email])
        clear_cache()


def clear_cache() -> None:
    """Forget cached accounts (and the parsed seed file); the next lookup re-reads the table."""
    global _store, _ready
    with _store_lock:
        _store = None
        _ready = False
    with _seed_lock:
        _seed_cache.clear()
