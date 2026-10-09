"""
Platform status and overview (sidebar health panel and welcome page).
"""

from backend.app.core.access import ROLE_DESCRIPTIONS, ROLE_TITLES, ROLES, allowed_routes
from backend.app.schemas.system import PlatformOverview, RoleCard, SystemStatus
from config.settings import ACTIVE_LLM_PROVIDER, APP_NAME, APP_TAGLINE, APP_VERSION
from src.utils.database import table_exists

PIPELINE_STAGES = ["Data", "Trust", "Intelligence", "Prediction", "Prescription", "Action"]


def get_system_status() -> SystemStatus:
    return SystemStatus(
        gold_ready=table_exists("gold_patient_360"),
        ml_ready=table_exists("model_registry"),
        llm_provider=ACTIVE_LLM_PROVIDER,
        version=APP_VERSION,
    )


def get_platform_overview() -> PlatformOverview:
    return PlatformOverview(
        app_name=APP_NAME,
        tagline=APP_TAGLINE,
        version=APP_VERSION,
        pipeline_stages=PIPELINE_STAGES,
        roles=[
            RoleCard(role=r, title=ROLE_TITLES[r], description=ROLE_DESCRIPTIONS[r], routes=allowed_routes(r))
            for r in ROLES
        ],
    )
