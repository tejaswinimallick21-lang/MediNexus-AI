"""
Access policy: three auth roles (admin, hcp, analyst) plus a persona per user.

The persona keeps the existing page-level rules from config/roles.py (e.g. the Receptionist
never sees clinical data); the role is the coarse gate. A page is reachable only when BOTH the
user's role and persona are allowed. Both UIs read this module, so the rules live in one place.
"""

from typing import Dict, FrozenSet, List, Tuple

from config.roles import ROLE_PERMISSIONS

ROLES = ("admin", "hcp", "analyst")

PERSONA_ROLE: Dict[str, str] = {
    "Data Engineer": "admin",
    "IT Administrator": "admin",
    "Doctor": "hcp",
    "Pharmacist": "hcp",
    "Laboratory Technician": "hcp",
    "Laboratory Specialist": "hcp",
    "Receptionist": "hcp",
    "Hospital Administrator": "analyst",
}

# API/React page key -> (Streamlit page key, React route)
PAGES: Dict[str, Tuple[str, str]] = {
    "reception": ("receptionist", "/reception"),
    "laboratory": ("laboratory", "/laboratory"),
    "pharmacy": ("pharmacist", "/pharmacy"),
    "executive": ("administrator", "/executive"),
    "it": ("it_admin", "/it"),
    "doctor": ("doctor", "/doctor"),
    "data": ("data_engineer", "/data"),
}


def page_policy(page: str) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """(allowed roles, allowed personas) for a page, derived from config/roles.py."""
    streamlit_page = PAGES[page][0]
    personas = frozenset(p for p, meta in ROLE_PERMISSIONS.items() if streamlit_page in meta.get("allowed_pages", []))
    roles = frozenset(PERSONA_ROLE[p] for p in personas if p in PERSONA_ROLE)
    return roles, personas


def can_access(role: str, persona: str, page: str) -> bool:
    roles, personas = page_policy(page)
    return role in roles and persona in personas and PERSONA_ROLE.get(persona) == role


def allowed_routes(role: str, persona: str) -> List[str]:
    """React routes the user may open, in sidebar order."""
    return [route for page, (_, route) in PAGES.items() if can_access(role, persona, page)]


def default_route(role: str, persona: str) -> str:
    default_page = ROLE_PERMISSIONS.get(persona, {}).get("default_page", "welcome")
    for page, (streamlit_page, route) in PAGES.items():
        if streamlit_page == default_page and can_access(role, persona, page):
            return route
    routes = allowed_routes(role, persona)
    return routes[0] if routes else "/"
