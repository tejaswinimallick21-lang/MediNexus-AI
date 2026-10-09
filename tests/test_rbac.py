"""
Tests for Authentication and Role-Based Access Control (RBAC) in MediNexus AI.
"""

import pytest
from src.security.auth import hash_password, verify_password, authenticate_user
from src.security.rbac import (
    check_page_access,
    check_table_access,
    check_action_access,
    get_allowed_pages,
)
from config.roles import (
    ROLE_DATA_ENGINEER,
    ROLE_DOCTOR,
    ROLE_PHARMACIST,
    ROLE_LAB_TECH,
    ROLE_RECEPTIONIST,
    ROLE_HOSPITAL_ADMIN,
    ROLE_IT_ADMIN,
)


def test_password_hashing_and_verification():
    """Verify that password hashing and verification function securely."""
    pwd = "SecureTestPassword@123"
    hashed = hash_password(pwd)

    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_user_authentication():
    """Verify demo user authentication against preconfigured accounts."""
    auth_doc = authenticate_user("dr_chen", "MediNexus@2026")
    assert auth_doc is not None
    assert auth_doc["role"] == ROLE_DOCTOR

    auth_fake = authenticate_user("dr_chen", "IncorrectPassword")
    assert auth_fake is None

    auth_nonexistent = authenticate_user("no_such_user", "MediNexus@2026")
    assert auth_nonexistent is None


def test_rbac_page_permissions():
    """Verify strict page access isolation between roles."""
    # Doctor permissions
    assert check_page_access(ROLE_DOCTOR, "doctor") is True
    assert check_page_access(ROLE_DOCTOR, "welcome") is True
    assert check_page_access(ROLE_DOCTOR, "receptionist") is False
    assert check_page_access(ROLE_DOCTOR, "data_engineer") is False

    # Receptionist permissions (Strictly no clinical or engineering access)
    assert check_page_access(ROLE_RECEPTIONIST, "receptionist") is True
    assert check_page_access(ROLE_RECEPTIONIST, "doctor") is False
    assert check_page_access(ROLE_RECEPTIONIST, "laboratory") is False
    assert check_page_access(ROLE_RECEPTIONIST, "data_engineer") is False

    # Data Engineer permissions
    assert check_page_access(ROLE_DATA_ENGINEER, "data_engineer") is True
    assert check_page_access(ROLE_DATA_ENGINEER, "doctor") is False


def test_rbac_table_permissions():
    """Verify table-level access controls."""
    # Doctor can access clinical tables but not unrestricted raw tables
    assert check_table_access(ROLE_DOCTOR, "gold_patient_360") is True
    assert check_table_access(ROLE_DOCTOR, "gold_admissions") is True

    # Receptionist restricted from clinical tables
    assert check_table_access(ROLE_RECEPTIONIST, "gold_patient_360") is False
    assert check_table_access(ROLE_RECEPTIONIST, "gold_laboratory") is False
    assert check_table_access(ROLE_RECEPTIONIST, "gold_appointments") is True
