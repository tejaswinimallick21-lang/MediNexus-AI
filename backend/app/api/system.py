"""
Public, non-sensitive platform metadata (shown on the welcome page and sidebar before sign-in).
"""

from fastapi import APIRouter

from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.system import PlatformOverview, SystemStatus
from backend.app.services import system as system_service

router = APIRouter(tags=["system"], responses=ERROR_RESPONSES)


@router.get("/system/status", response_model=SystemStatus)
def system_status() -> SystemStatus:
    return system_service.get_system_status()


@router.get("/platform/overview", response_model=PlatformOverview)
def platform_overview() -> PlatformOverview:
    return system_service.get_platform_overview()
