"""
MediNexus AI FastAPI backend.

Run from the project root:  python -m uvicorn backend.app.main:app --reload --port 8000
"""

import logging
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
    yield


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

    install_error_handlers(app)
    for router in routers:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
