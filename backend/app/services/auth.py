"""
Authentication service used by the FastAPI auth router.
"""

from typing import Optional

from backend.app.core.access import ROLE_TITLES, allowed_routes, default_route
from backend.app.core.security import verify_password
from backend.app.core.users import UserRecord, get_user
from backend.app.schemas.auth import UserOut
from src.security.audit import log_audit_event


def authenticate(email: str, password: str) -> Optional[UserRecord]:
    """Return the user for valid credentials; audit both outcomes (never the password)."""
    user = get_user(email or "")
    ok = user is not None and verify_password(password, user.password_hash)
    log_audit_event(
        username=(email or "").strip().lower(),
        role=user.role if user else "unknown",
        action="LOGIN" if ok else "LOGIN_FAILED",
        resource="SYSTEM_AUTH",
        status="SUCCESS" if ok else "FAILED",
        details="Credential sign-in" if ok else "Invalid email or password",
    )
    return user if ok else None


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
    )
