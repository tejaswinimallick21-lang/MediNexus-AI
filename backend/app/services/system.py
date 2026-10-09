"""
Platform status and overview (sidebar readiness panel and welcome page).
"""

from backend.app.core.access import PAGES, PERSONA_ROLE, page_policy
from backend.app.schemas.system import PersonaCard, PlatformOverview, SystemStatus
from config.roles import ROLE_PERMISSIONS
from config.settings import ACTIVE_LLM_PROVIDER, APP_NAME, APP_TAGLINE, APP_VERSION
from src.utils.database import table_exists

PIPELINE_STAGES = ["Data", "Trust", "Intelligence", "Prediction", "Prescription", "Action"]
PERSONA_ORDER = ["Data Engineer", "Doctor", "Hospital Administrator", "Pharmacist",
                 "Laboratory Technician", "Receptionist", "IT Administrator"]


def get_system_status() -> SystemStatus:
    return SystemStatus(
        gold_ready=table_exists("gold_patient_360"),
        ml_ready=table_exists("model_registry"),
        llm_provider=ACTIVE_LLM_PROVIDER,
        version=APP_VERSION,
    )


def get_platform_overview() -> PlatformOverview:
    cards = []
    for persona in PERSONA_ORDER:
        meta = ROLE_PERMISSIONS[persona]
        route = next(
            (r for page, (sp, r) in PAGES.items() if sp == meta.get("default_page") and persona in page_policy(page)[1]),
            "/",
        )
        cards.append(PersonaCard(
            persona=persona,
            role=PERSONA_ROLE[persona],
            title=meta["title"],
            description=meta["description"],
            route=route,
        ))
    return PlatformOverview(
        app_name=APP_NAME, tagline=APP_TAGLINE, version=APP_VERSION,
        pipeline_stages=PIPELINE_STAGES, personas=cards,
    )
