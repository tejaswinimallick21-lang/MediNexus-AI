"""
Password hashing (bcrypt) and session tokens (JWT, carried in an httpOnly cookie).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
import jwt

from backend.app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session_token(email: str, version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": email, "ver": version, "iat": now, "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_session(token: str) -> Optional[Tuple[str, int]]:
    """(email, account session version) for a valid, unexpired token; None otherwise."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    sub, ver = payload.get("sub"), payload.get("ver", 0)
    return (sub, int(ver)) if isinstance(sub, str) and isinstance(ver, int) else None


def decode_session_token(token: str) -> Optional[str]:
    """Return the email in a valid, unexpired token; None otherwise."""
    session = decode_session(token)
    return session[0] if session else None
