"""
System Settings and Environment Configuration for MediNexus AI.
"""

import os
from pathlib import Path
from typing import Dict, Any

from config.constants import (
    BASE_DIR,
    DATA_DIR,
    RAW_DATA_DIR,
    BRONZE_DATA_DIR,
    SILVER_DATA_DIR,
    GOLD_DATA_DIR,
    METADATA_DIR,
    ML_RESULTS_DIR,
    DATABASE_DIR,
    DATABASE_PATH,
    MODELS_DIR,
    DOCUMENTS_DIR,
    LOGS_DIR,
)

# Application Metadata
APP_NAME = "MediNexus AI"
APP_TAGLINE = "Role-Based Healthcare Data-to-Decision Intelligence Platform"
APP_VERSION = "2.4.0"
RANDOM_SEED = 42

# Environment Variables Loading (Simple .env parser without external dependencies)
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Check Streamlit Cloud secrets if running hosted on Streamlit Cloud
_st_secrets = {}
try:
    import streamlit as st
    if hasattr(st, "secrets"):
        _st_secrets = dict(st.secrets)
except Exception:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or str(_st_secrets.get("GEMINI_API_KEY", ""))
ENABLE_GEMINI = bool(GEMINI_API_KEY and len(GEMINI_API_KEY) > 10)

# xAI Grok API Configuration
GROK_API_KEY = os.getenv("GROK_API_KEY", "") or os.getenv("XAI_API_KEY", "") or str(_st_secrets.get("GROK_API_KEY", ""))
ENABLE_GROK = bool(GROK_API_KEY and len(GROK_API_KEY) > 10)
GROK_MODEL = os.getenv("GROK_MODEL", "grok-beta") or str(_st_secrets.get("GROK_MODEL", "grok-beta"))

# Active Provider Detection
if ENABLE_GROK:
    ACTIVE_LLM_PROVIDER = f"Grok ({GROK_MODEL})"
elif ENABLE_GEMINI:
    ACTIVE_LLM_PROVIDER = "Gemini 1.5 Flash"
else:
    ACTIVE_LLM_PROVIDER = "Deterministic Local Engine"

# Preconfigured Demo Users
# Note: In production, passwords are stored as secure hashes.
# Default password for all demo accounts is: "MediNexus@2026"
DEMO_PASSWORD_DEFAULT = "MediNexus@2026"

DEMO_USERS: Dict[str, Dict[str, Any]] = {
    "data_engineer": {
        "username": "data_engineer",
        "name": "Data Engineer",
        "email": "data.engineer@medinexus.org",
        "role": "Data Engineer",
        "department": "Data Platform & Engineering",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "dr_chen": {
        "username": "dr_chen",
        "name": "Doctor",
        "email": "doctor@medinexus.org",
        "role": "Doctor",
        "department": "Internal Medicine & Cardiology",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "admin_holloway": {
        "username": "admin_holloway",
        "name": "Hospital Administrator",
        "email": "admin@medinexus.org",
        "role": "Hospital Administrator",
        "department": "Executive Operations",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "pharmacist_patel": {
        "username": "pharmacist_patel",
        "name": "Pharmacist",
        "email": "pharmacist@medinexus.org",
        "role": "Pharmacist",
        "department": "Central Clinical Pharmacy",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "lab_tech_kim": {
        "username": "lab_tech_kim",
        "name": "Laboratory Specialist",
        "email": "lab@medinexus.org",
        "role": "Laboratory Technician",
        "department": "Pathology & Diagnostics",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "receptionist_davis": {
        "username": "receptionist_davis",
        "name": "Receptionist",
        "email": "receptionist@medinexus.org",
        "role": "Receptionist",
        "department": "Outpatient Registration & Care Flow",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
    "it_admin_torvalds": {
        "username": "it_admin_torvalds",
        "name": "IT Administrator",
        "email": "it.admin@medinexus.org",
        "role": "IT Administrator",
        "department": "Information Security & Infrastructure",
        "plain_pwd": DEMO_PASSWORD_DEFAULT,
    },
}


def ensure_directories():
    """Ensure all required project directories exist."""
    directories = [
        DATA_DIR,
        RAW_DATA_DIR,
        BRONZE_DATA_DIR,
        SILVER_DATA_DIR,
        GOLD_DATA_DIR,
        METADATA_DIR,
        ML_RESULTS_DIR,
        DATABASE_DIR,
        MODELS_DIR,
        DOCUMENTS_DIR,
        LOGS_DIR,
        DOCUMENTS_DIR / "hospital_policies",
        DOCUMENTS_DIR / "clinical_guidelines",
        DOCUMENTS_DIR / "pharmacy",
        DOCUMENTS_DIR / "laboratory",
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)


ensure_directories()
