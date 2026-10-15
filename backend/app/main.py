"""
MediNexus AI FastAPI backend.

Run from the project root:  python -m uvicorn backend.app.main:app --reload --port 8000
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.errors import install_error_handlers
from backend.app.core.users import load_users
from backend.app.api import routers

logger = logging.getLogger("medinexus.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_users()  # fail fast with a clear message when the seed file is missing
    if settings.jwt_secret_is_ephemeral:
        logger.warning("MEDINEXUS_JWT_SECRET not set: using a per-process signing key (sessions reset on restart).")
    from backend.app.agents.sweep import start_scheduler

    stop = threading.Event()
    start_scheduler(stop)  # daily Nexa morning sweep (NEXA_SWEEP_ENABLED=0 turns it off)
    from backend.app.services.data_feed import start_scheduler as start_feed

    start_feed(stop)  # nightly live data feed (MEDINEXUS_FEED_ENABLED=0 turns it off)
    yield
    stop.set()


def create_app() -> FastAPI:
    app = FastAPI(title=f"{settings.app_name} API", version=settings.app_version, lifespan=lifespan)

    if settings.cors_origins:  # development only
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request, call_next):
        """Baseline hardening headers on every API response (the API serves JSON, never HTML pages to frame)."""
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    install_error_handlers(app)
    for router in routers:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
