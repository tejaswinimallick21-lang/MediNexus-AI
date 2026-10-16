"""
Access policy: three roles, one account each.

    admin    Platform administrator   every workspace (oversight), plus Data Engineering and Security
    hcp      Healthcare professional  Oncology Workstation, Pharmacy, Laboratory
    analyst  Operations analyst       Oncology Outcomes, Analyst Command Center, Patient Access

Both the API (per-request checks) and the React app (navigation) read this module.
"""

from typing import Dict, FrozenSet, List

ROLES = ("admin", "hcp", "analyst")

ROLE_TITLES: Dict[str, str] = {
    "admin": "Platform Administrator",
    "hcp": "Healthcare Professional",
    "analyst": "Operations Analyst",
}

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "admin": "Oversees the whole network: every workspace, plus the data pipeline, model registry, agent governance and audit trail.",
    "hcp": "Oncology decision support: tumour-board worklist, Patient 360 and treatment pathway, mortality risk, care gaps, chemotherapy stock and laboratory operations.",
    "analyst": "Oncology outcomes and operations: survival by type and stage, time to treatment, cost of care, treatment capacity and outpatient access.",
}

# API page key -> (React route, roles allowed)
PAGES: Dict[str, tuple] = {
    "data": ("/data", frozenset({"admin"})),
    "it": ("/it", frozenset({"admin"})),
    "doctor": ("/doctor", frozenset({"hcp", "admin"})),
    "pharmacy": ("/pharmacy", frozenset({"hcp", "admin"})),
    "laboratory": ("/laboratory", frozenset({"hcp", "admin"})),
    "executive": ("/executive", frozenset({"analyst", "admin"})),
    "command": ("/command-center", frozenset({"analyst", "admin"})),
    "reception": ("/reception", frozenset({"analyst", "admin"})),
}

# AI copilots each role may use
AGENT_ROLES: Dict[str, FrozenSet[str]] = {
    "medicare": frozenset({"hcp", "admin"}),
    "pharmalab": frozenset({"hcp", "admin"}),
    "healthanalyst": frozenset({"analyst", "admin"}),
    "ops": frozenset({"admin"}),
}


def can_access(role: str, page: str) -> bool:
    return page in PAGES and role in PAGES[page][1]


def allowed_routes(role: str) -> List[str]:
    """React routes the role may open, in sidebar order."""
    return [route for route, roles in PAGES.values() if role in roles]


DEFAULT_ROUTES = {"admin": "/", "hcp": "/doctor", "analyst": "/executive"}  # admin lands on Platform Overview


def default_route(role: str) -> str:
    return DEFAULT_ROUTES.get(role, "/")
