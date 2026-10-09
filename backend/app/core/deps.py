"""
Request dependencies: the signed-in user and per-page role checks.
"""

from typing import Callable

from fastapi import Depends, Request

from backend.app.core.access import AGENT_ROLES, can_access
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


def _deny(user: UserRecord, resource: str) -> None:
    log_audit_event(
        username=user.email, role=user.role, action="ACCESS_DENIED",
        resource=resource, status="BLOCKED", details=f"Role '{user.role}' attempted to access {resource}",
    )
    raise APIError(403, "forbidden", f"Your role is not authorized for this resource.")


def require_page(page: str) -> Callable[..., UserRecord]:
    """Dependency factory: the user's role must own `page`."""

    def _check(user: UserRecord = Depends(current_user)) -> UserRecord:
        if not can_access(user.role, page):
            _deny(user, f"API_{page.upper()}")
        return user

    return _check


def require_agent(agent: str, user: UserRecord) -> None:
    if user.role not in AGENT_ROLES.get(agent, frozenset()):
        _deny(user, f"AGENT_{agent.upper()}")
