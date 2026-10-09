"""
Access policy: three roles, one account each.

    admin    Platform administrator   every workspace (oversight), plus Data Engineering and Security
    hcp      Healthcare professional  Clinical Workstation, Pharmacy, Laboratory
    analyst  Operations analyst       Executive Operations, Patient Access

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
    "hcp": "Clinical decision support: patient 360, risk predictions, care plans, pharmacy stock and laboratory operations.",
    "analyst": "Enterprise performance: occupancy, readmissions, revenue, capacity planning and outpatient patient access.",
}

# API page key -> (React route, roles allowed)
PAGES: Dict[str, tuple] = {
    "data": ("/data", frozenset({"admin"})),
    "it": ("/it", frozenset({"admin"})),
    "doctor": ("/doctor", frozenset({"hcp", "admin"})),
    "pharmacy": ("/pharmacy", frozenset({"hcp", "admin"})),
    "laboratory": ("/laboratory", frozenset({"hcp", "admin"})),
    "executive": ("/executive", frozenset({"analyst", "admin"})),
    "reception": ("/reception", frozenset({"analyst", "admin"})),
}

# AI copilots each role may use
AGENT_ROLES: Dict[str, FrozenSet[str]] = {
    "medicare": frozenset({"hcp", "admin"}),
    "pharmalab": frozenset({"hcp", "admin"}),
    "healthanalyst": frozenset({"analyst", "admin"}),
}


def can_access(role: str, page: str) -> bool:
    return page in PAGES and role in PAGES[page][1]


def allowed_routes(role: str) -> List[str]:
    """React routes the role may open, in sidebar order."""
    return [route for route, roles in PAGES.values() if role in roles]


DEFAULT_ROUTES = {"admin": "/data", "hcp": "/doctor", "analyst": "/executive"}


def default_route(role: str) -> str:
    return DEFAULT_ROUTES.get(role, "/")
