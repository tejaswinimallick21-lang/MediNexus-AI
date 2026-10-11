"""
People management for administrators: add people, change role or details, disable or re-enable,
and reset passwords. Every change is audited (never a password).

Safety rules: administrators cannot change their own role, disable or reset themselves (they use
"Change password"), and the last active administrator cannot be removed.
"""

import secrets
import string
from datetime import datetime

from backend.app.core.access import ROLE_TITLES
from backend.app.core.errors import APIError
from backend.app.core.security import hash_password
from backend.app.core.users import UserRecord, get_user, insert_user, list_users, update_user
from backend.app.schemas.users import TemporaryPassword, UserAdminRow, UserCreateIn, UserDirectory, UserUpdateIn
from src.security.audit import log_audit_event

_ALPHABET = string.ascii_letters + string.digits


def temporary_password(length: int = 14) -> str:
    """Random letters and digits (always both), for one-time use."""
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def _iso(ts) -> str | None:
    return ts.isoformat(timespec="seconds") if ts else None


def _row(u: UserRecord, me: UserRecord) -> UserAdminRow:
    return UserAdminRow(
        email=u.email, name=u.name, role=u.role, role_title=ROLE_TITLES[u.role], department=u.department,
        active=u.active, must_change_password=u.must_change_password, created_at=_iso(u.created_at),
        created_by=u.created_by, last_login_at=_iso(u.last_login_at), is_you=u.email == me.email,
    )


def directory(me: UserRecord) -> UserDirectory:
    users = list_users()
    return UserDirectory(
        users=[_row(u, me) for u in users],
        active_count=sum(u.active for u in users),
        admin_count=sum(u.active and u.role == "admin" for u in users),
    )


def _target(email: str) -> UserRecord:
    user = get_user(email)
    if user is None:
        raise APIError(404, "user_not_found", "No account with that email.")
    return user


def _audit(me: UserRecord, action: str, email: str, details: str) -> None:
    log_audit_event(username=me.email, role=me.role, action=action, resource=f"USER:{email}", status="SUCCESS", details=details)


def create(body: UserCreateIn, me: UserRecord) -> TemporaryPassword:
    if get_user(body.email):
        raise APIError(409, "user_exists", "An account with that email already exists.")
    password = temporary_password()
    insert_user(UserRecord(
        email=body.email, name=body.name, role=body.role, department=body.department, password_hash=hash_password(password),
        active=True, must_change_password=True, password_changed_at=None, created_at=datetime.now(), created_by=me.email,
        last_login_at=None, session_version=0,
    ))
    _audit(me, "USER_CREATE", body.email, f"role={body.role}")
    return TemporaryPassword(user=_row(get_user(body.email), me), temporary_password=password)


def update(email: str, body: UserUpdateIn, me: UserRecord) -> UserAdminRow:
    user = _target(email)
    changes = body.model_dump(exclude_none=True)
    changes = {k: (v.strip() if isinstance(v, str) else v) for k, v in changes.items() if getattr(user, k) != v}
    if not changes:
        return _row(user, me)
    if user.email == me.email and ("role" in changes or changes.get("active") is False):
        raise APIError(409, "cannot_modify_self", "You cannot change your own role or disable your own account.")
    removes_admin = user.role == "admin" and user.active and (changes.get("role", "admin") != "admin" or changes.get("active") is False)
    if removes_admin and sum(u.active and u.role == "admin" for u in list_users()) <= 1:
        raise APIError(409, "last_admin", "At least one active administrator must remain.")
    if changes.get("active") is False:
        changes["session_version"] = user.session_version + 1  # signs them out everywhere
    update_user(user.email, **changes)
    if "active" in changes:
        _audit(me, "USER_ENABLE" if changes["active"] else "USER_DISABLE", user.email,
               "Account re-enabled" if changes["active"] else "Account disabled; active sessions ended")
    other = {k: v for k, v in changes.items() if k not in ("active", "session_version")}
    if other:
        _audit(me, "USER_UPDATE", user.email, ", ".join(f"{k}={v}" for k, v in other.items()))
    return _row(get_user(user.email), me)


def reset_password(email: str, me: UserRecord) -> TemporaryPassword:
    user = _target(email)
    if user.email == me.email:
        raise APIError(409, "cannot_modify_self", "Use Change password for your own account.")
    password = temporary_password()
    update_user(user.email, password_hash=hash_password(password), must_change_password=True, password_changed_at=datetime.now(),
                session_version=user.session_version + 1)
    _audit(me, "PASSWORD_RESET", user.email, "Temporary password issued; active sessions ended")
    return TemporaryPassword(user=_row(get_user(user.email), me), temporary_password=password)
