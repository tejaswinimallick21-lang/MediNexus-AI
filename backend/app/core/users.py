"""
User store loaded from the .gitignored seed file (backend/seed_users.json).
Create it with: npm run seed  (python -m backend.scripts.create_seed_users)
"""

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

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


class SeedFileError(RuntimeError):
    pass


_lock = threading.Lock()
_cache: Dict[Path, Dict[str, UserRecord]] = {}


def load_users(path: Optional[Path] = None) -> Dict[str, UserRecord]:
    """Parse and validate the seed file once per path; keyed by lower-case email."""
    path = Path(path or settings.seed_file)
    with _lock:
        if path in _cache:
            return _cache[path]
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
        _cache[path] = users
        return users


def get_user(email: str) -> Optional[UserRecord]:
    return load_users().get(email.strip().lower())


def clear_cache() -> None:
    with _lock:
        _cache.clear()
