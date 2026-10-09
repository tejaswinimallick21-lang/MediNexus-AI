"""
Request dependencies: the signed-in user and per-page role + persona checks.
"""

from typing import Callable

from fastapi import Depends, Request

from backend.app.core.access import can_access
from backend.app.core.config import settings
from backend.app.core.errors import APIError
from backend.app.core.security import decode_session_token
from backend.app.core.users import UserRecord, get_user
from src.security.audit import log_audit_event


def current_user(request: Request) -> UserRecord:
    token = request.cookies.get(settings.cookie_name)
    email = decode_session_token(token) if token else None
    user = get_user(email) if email else None
    if user is None:
        raise APIError(401, "not_authenticated", "Sign in to continue.")
    return user


def require_page(page: str) -> Callable[..., UserRecord]:
    """Dependency factory: the user must hold a role AND persona allowed on `page`."""

    def _check(user: UserRecord = Depends(current_user)) -> UserRecord:
        if not can_access(user.role, user.persona, page):
            log_audit_event(
                username=user.email,
                role=user.persona,
                action="ACCESS_DENIED",
                resource=f"API_{page.upper()}",
                status="BLOCKED",
                details=f"{user.role}/{user.persona} attempted to access {page}",
            )
            raise APIError(403, "forbidden", f"Your role is not authorized for {page}.")
        return user

    return _check
