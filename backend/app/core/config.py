"""
Backend runtime settings. Values come from environment variables (the project-root .env is
loaded by config.settings); development defaults keep `npm run backend` zero-config.
"""

import os
import secrets
import sys
from pathlib import Path

# Make the project root importable (config/, src/) regardless of the working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings as app_settings  # noqa: E402  (loads .env into os.environ)

BACKEND_DIR = PROJECT_ROOT / "backend"


class Settings:
    env: str = os.getenv("MEDINEXUS_ENV", "development")
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = int(os.getenv("MEDINEXUS_JWT_TTL_MINUTES", "480"))
    cookie_name: str = "medinexus_session"
    cookie_secure: bool = os.getenv("MEDINEXUS_COOKIE_SECURE", "false").lower() == "true"
    seed_file: Path = Path(os.getenv("MEDINEXUS_SEED_FILE", str(BACKEND_DIR / "seed_users.json")))
    app_name: str = app_settings.APP_NAME
    app_version: str = app_settings.APP_VERSION

    def __init__(self) -> None:
        configured = os.getenv("MEDINEXUS_JWT_SECRET", "")
        # Without a configured secret, sessions are signed with a per-process key (dev only):
        # restarting the backend signs everyone out, which is acceptable locally.
        self.jwt_secret: str = configured or secrets.token_urlsafe(48)
        self.jwt_secret_is_ephemeral: bool = not configured

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def cors_origins(self) -> list[str]:
        return ["http://localhost:5173"] if self.is_development else []


settings = Settings()
