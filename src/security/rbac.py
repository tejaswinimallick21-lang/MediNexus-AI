"""
Role-Based Access Control (RBAC) Enforcement Engine for MediNexus AI.
"""

from typing import List, Dict, Any, Optional
from config.roles import ROLE_PERMISSIONS, ALL_ROLES


def is_role_valid(role: Optional[str]) -> bool:
    """Check if a given role is recognized."""
    return bool(role and role in ROLE_PERMISSIONS)


def get_role_metadata(role: Optional[str]) -> Dict[str, Any]:
    """Retrieve RBAC policy definition for a role."""
    if not role or role not in ROLE_PERMISSIONS:
        return {
            "title": "Guest",
            "description": "Unauthorized access",
            "allowed_pages": ["welcome"],
            "default_page": "welcome",
            "accessible_layers": [],
            "accessible_tables": [],
            "allowed_actions": [],
            "allowed_agents": [],
        }
    return ROLE_PERMISSIONS[role]


def check_page_access(role: Optional[str], page_name: str) -> bool:
    """Verify if role has authorization to access the specified page."""
    if not role or role not in ROLE_PERMISSIONS:
        return page_name == "welcome"
    allowed_pages = ROLE_PERMISSIONS[role].get("allowed_pages", [])
    return page_name in allowed_pages or page_name == "welcome"


def check_table_access(role: Optional[str], table_name: str) -> bool:
    """Verify if role has authorization to access specific DuckDB / Parquet table."""
    if not role or role not in ROLE_PERMISSIONS:
        return False
    accessible_tables = ROLE_PERMISSIONS[role].get("accessible_tables", [])
    if "*" in accessible_tables:
        return True
    return table_name in accessible_tables


def check_action_access(role: Optional[str], action_name: str) -> bool:
    """Verify if role has permission to execute specific operational action."""
    if not role or role not in ROLE_PERMISSIONS:
        return False
    allowed_actions = ROLE_PERMISSIONS[role].get("allowed_actions", [])
    return action_name in allowed_actions


def check_agent_access(role: Optional[str], agent_name: str) -> bool:
    """Verify if role has permission to interact with specific AI Agent."""
    if not role or role not in ROLE_PERMISSIONS:
        return False
    allowed_agents = ROLE_PERMISSIONS[role].get("allowed_agents", [])
    return agent_name in allowed_agents


def get_allowed_pages(role: Optional[str]) -> List[str]:
    """Get list of pages accessible to a given role."""
    if not role or role not in ROLE_PERMISSIONS:
        return ["welcome"]
    return ROLE_PERMISSIONS[role].get("allowed_pages", ["welcome"])
