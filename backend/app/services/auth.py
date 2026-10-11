"""
Authentication service used by the FastAPI auth router.

Brute-force protection (POL-IT-001): 5 failed sign-ins for an account within 15 minutes lock that
account for 15 minutes. The lock is per account and in memory (it resets when the API restarts).
"""

import os
import re
import threading
import time
from datetime import datetime
from collections import deque
from typing import Deque, Dict, Optional

from backend.app.core.access import ROLE_TITLES, allowed_routes, default_route
from backend.app.core.errors import APIError
from backend.app.core.security import hash_password, verify_password
from backend.app.core.users import UserRecord, get_user, update_user
from backend.app.schemas.auth import UserOut
from src.security.audit import log_audit_event

MAX_FAILURES = int(os.getenv("MEDINEXUS_LOGIN_MAX_FAILURES", "5"))
WINDOW_SECONDS = int(os.getenv("MEDINEXUS_LOGIN_WINDOW_SECONDS", "900"))
LOCK_SECONDS = int(os.getenv("MEDINEXUS_LOGIN_LOCK_SECONDS", "900"))

_failures: Dict[str, Deque[float]] = {}
_locked_until: Dict[str, float] = {}
_lock = threading.Lock()


def lockout_state() -> Dict[str, float]:
    """Accounts currently locked, with seconds remaining (for the security workspace)."""
    now = time.time()
    with _lock:
        return {k: round(v - now) for k, v in _locked_until.items() if v > now}


def _check_locked(key: str) -> None:
    with _lock:
        until = _locked_until.get(key, 0)
    if until > time.time():
        minutes = max(1, round((until - time.time()) / 60))
        raise APIError(429, "account_locked", f"Too many failed sign-ins. Try again in about {minutes} minute{'s' if minutes != 1 else ''}.")


def _record_failure(key: str) -> bool:
    """Returns True when this failure locks the account."""
    now = time.time()
    with _lock:
        q = _failures.setdefault(key, deque())
        q.append(now)
        while q and q[0] < now - WINDOW_SECONDS:
            q.popleft()
        if len(q) >= MAX_FAILURES:
            _locked_until[key] = now + LOCK_SECONDS
            q.clear()
            return True
    return False


def authenticate(email: str, password: str) -> Optional[UserRecord]:
    """Return the user for valid credentials; audit both outcomes (never the password)."""
    key = (email or "").strip().lower()
    _check_locked(key)
    user = get_user(email or "")
    valid = user is not None and verify_password(password, user.password_hash)
    ok = valid and user.active
    log_audit_event(
        username=key,
        role=user.role if user else "unknown",
        action="LOGIN" if ok else "LOGIN_FAILED",
        resource="SYSTEM_AUTH",
        status="SUCCESS" if ok else "FAILED",
        details="Credential sign-in" if ok else ("Account disabled" if valid else "Invalid email or password"),
    )
    if ok:
        with _lock:
            _failures.pop(key, None)
        update_user(user.email, last_login_at=datetime.now())
        return get_user(user.email)
    if valid:  # right password, disabled account: refuse without counting towards a lockout
        return None
    if _record_failure(key):
        log_audit_event(username=key, role=user.role if user else "unknown", action="ACCOUNT_LOCKED", resource="SYSTEM_AUTH", status="BLOCKED",
                        details=f"{MAX_FAILURES} failed sign-ins within {WINDOW_SECONDS // 60} minutes; locked for {LOCK_SECONDS // 60} minutes")
    return None


def record_logout(user: UserRecord) -> None:
    log_audit_event(
        username=user.email, role=user.role, action="LOGOUT",
        resource="SYSTEM_AUTH", status="SUCCESS", details="Signed out",
    )


def to_user_out(user: UserRecord) -> UserOut:
    return UserOut(
        email=user.email,
        name=user.name,
        role=user.role,
        role_title=ROLE_TITLES[user.role],
        department=user.department,
        allowed_routes=allowed_routes(user.role),
        default_route=default_route(user.role),
        must_change_password=user.must_change_password,
    )


# ---- passwords -----------------------------------------------------------------------------------

MIN_PASSWORD = 10
DEMO_PASSWORD = "MediNexus@2026"


def check_password_policy(password: str, email: str) -> None:
    """At least 10 characters with a letter and a digit; not the email or the public demo password."""
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"at least {MIN_PASSWORD} characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("a letter and a number")
    if problems:
        raise APIError(422, "weak_password", "Password needs " + " and ".join(problems) + ".")
    if password.lower() in (email.lower(), email.split("@")[0].lower()) or password == DEMO_PASSWORD:
        raise APIError(422, "weak_password", "Choose a password that is not your email or the demo password.")


def change_password(user: UserRecord, current_password: str, new_password: str) -> UserRecord:
    """The signed-in user's own change; ends their other sessions (the caller re-issues this one)."""
    if not verify_password(current_password, user.password_hash):
        log_audit_event(username=user.email, role=user.role, action="PASSWORD_CHANGE", resource="SYSTEM_AUTH",
                        status="FAILED", details="Current password incorrect")
        raise APIError(400, "wrong_password", "Your current password is incorrect.")
    if new_password == current_password:
        raise APIError(422, "weak_password", "Choose a password different from the current one.")
    check_password_policy(new_password, user.email)
    update_user(user.email, password_hash=hash_password(new_password), must_change_password=False, password_changed_at=datetime.now(),
                session_version=user.session_version + 1)
    log_audit_event(username=user.email, role=user.role, action="PASSWORD_CHANGE", resource="SYSTEM_AUTH",
                    status="SUCCESS", details="Changed own password")
    return get_user(user.email)
