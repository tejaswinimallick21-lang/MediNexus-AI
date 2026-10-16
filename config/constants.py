"""
Constants and Schema Definitions for MediNexus AI.
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
BRONZE_DATA_DIR = DATA_DIR / "bronze"
SILVER_DATA_DIR = DATA_DIR / "silver"
GOLD_DATA_DIR = DATA_DIR / "gold"
METADATA_DIR = DATA_DIR / "metadata"
ML_RESULTS_DIR = DATA_DIR / "ml_results"
DATABASE_DIR = BASE_DIR / "database"
# Overridable so tests (and other environments) can use their own copy of the database
DATABASE_PATH = Path(os.environ["MEDINEXUS_DB_PATH"]) if os.getenv("MEDINEXUS_DB_PATH") else DATABASE_DIR / "healthcare.duckdb"
MODELS_DIR = BASE_DIR / "models"
DOCUMENTS_DIR = BASE_DIR / "documents"
LOGS_DIR = Path(os.environ["MEDINEXUS_LOGS_DIR"]) if os.getenv("MEDINEXUS_LOGS_DIR") else BASE_DIR / "logs"

# Synthea source export (CSV). Swap to the 100K export by pointing this at its folder.
SYNTHEA_CSV_DIR = DATA_DIR / "synthea" / "current"  # the prepared oncology dataset (src/ingestion/oncology_dataset.py)

# 30-day window used for unplanned readmissions
OUTCOME_WINDOW_DAYS = 30

# Default Generation Counts (Enterprise Scale: 50,000+ records in each core dataset)
DEFAULT_COUNTS = {
    "patients": 50000,
    "admissions": 55000,
    "diagnoses": 75000,
    "laboratory_results": 100000,
    "medications": 200,
    "prescriptions": 80000,
    "appointments": 60000,
    "billing": 55000,
    "hospitals": 10,
    "doctors": 500,
    "pharmacy_inventory": 2500,
    "departments": 25,
}

# Standard Demo Scale (Lightweight dev mode)
LIGHT_COUNTS = {
    "patients": 3500,
    "admissions": 5000,
    "diagnoses": 7500,
    "laboratory_results": 15000,
    "medications": 50,
    "prescriptions": 12000,
    "appointments": 8000,
    "billing": 5000,
    "hospitals": 5,
    "doctors": 40,
    "pharmacy_inventory": 250,
    "departments": 8,
}

# Core Healthcare Tables
DATASETS = [
    "hospitals",
    "departments",
    "doctors",
    "patients",
    "admissions",
    "diagnoses",
    "laboratory_results",
    "medications",
    "prescriptions",
    "pharmacy_inventory",
    "appointments",
    "billing",
]

# Gold Models
GOLD_TABLES = [
    "gold_patient_360",
    "gold_admissions",
    "gold_clinical",
    "gold_laboratory",
    "gold_pharmacy",
    "gold_prescriptions",
    "gold_appointments",
    "gold_billing",
    "gold_hospital_operations",
    "gold_patient_risk_features",
    "gold_outcome_risk",
]

# Clinical Standard Values
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
GENDERS = ["Male", "Female", "Other"]
ADMISSION_TYPES = ["Emergency", "Elective", "Urgent"]
DISCHARGE_DISPOSITIONS = ["Home", "Transferred", "Rehabilitation", "Hospice", "Deceased"]
PAYMENT_STATUSES = ["Paid", "Pending", "Overdue"]
APPOINTMENT_STATUSES = ["Completed", "Scheduled", "Cancelled", "No-Show"]
DIAGNOSIS_TYPES = ["Primary", "Secondary"]
DIAGNOSIS_SEVERITIES = ["Mild", "Moderate", "Severe"]
ABNORMAL_FLAGS = ["Normal", "High", "Low", "Critical"]

# Medical ICD-10 Reference Sample
ICD10_CATALOG = [
    {"code": "I10", "description": "Essential (primary) hypertension", "severity": "Moderate"},
    {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications", "severity": "Moderate"},
    {"code": "J44.9", "description": "Chronic obstructive pulmonary disease, unspecified", "severity": "Severe"},
    {"code": "I50.9", "description": "Heart failure, unspecified", "severity": "Severe"},
    {"code": "N18.9", "description": "Chronic kidney disease, unspecified", "severity": "Severe"},
    {"code": "J18.9", "description": "Pneumonia, unspecified organism", "severity": "Moderate"},
    {"code": "K21.9", "description": "Gastro-esophageal reflux disease without esophagitis", "severity": "Mild"},
    {"code": "M54.5", "description": "Low back pain", "severity": "Mild"},
    {"code": "F32.9", "description": "Major depressive disorder, single episode", "severity": "Moderate"},
    {"code": "I21.9", "description": "Acute myocardial infarction, unspecified", "severity": "Severe"},
    {"code": "A41.9", "description": "Sepsis, unspecified organism", "severity": "Severe"},
    {"code": "C34.90", "description": "Malignant neoplasm of unspecified part of bronchus or lung", "severity": "Severe"},
]

# Lab Tests Catalog
LAB_CATALOG = [
    {"name": "Fasting Blood Glucose", "category": "Biochemistry", "unit": "mg/dL", "low": 70, "high": 99, "crit_high": 250, "crit_low": 45},
    {"name": "HbA1c", "category": "Biochemistry", "unit": "%", "low": 4.0, "high": 5.6, "crit_high": 10.0, "crit_low": 3.0},
    {"name": "Serum Creatinine", "category": "Biochemistry", "unit": "mg/dL", "low": 0.7, "high": 1.3, "crit_high": 4.0, "crit_low": 0.3},
    {"name": "White Blood Cell Count (WBC)", "category": "Hematology", "unit": "10^3/uL", "low": 4.5, "high": 11.0, "crit_high": 25.0, "crit_low": 2.0},
    {"name": "Hemoglobin", "category": "Hematology", "unit": "g/dL", "low": 12.0, "high": 17.5, "crit_high": 20.0, "crit_low": 7.0},
    {"name": "Platelet Count", "category": "Hematology", "unit": "10^3/uL", "low": 150, "high": 450, "crit_high": 800, "crit_low": 50},
    {"name": "Troponin-I", "category": "Cardiac", "unit": "ng/mL", "low": 0.0, "high": 0.04, "crit_high": 0.5, "crit_low": 0.0},
    {"name": "Total Cholesterol", "category": "Lipid", "unit": "mg/dL", "low": 125, "high": 200, "crit_high": 300, "crit_low": 90},
    {"name": "Serum Potassium", "category": "Electrolytes", "unit": "mEq/L", "low": 3.5, "high": 5.0, "crit_high": 6.5, "crit_low": 2.8},
    {"name": "C-Reactive Protein (CRP)", "category": "Immunology", "unit": "mg/L", "low": 0.0, "high": 3.0, "crit_high": 50.0, "crit_low": 0.0},
]

# Essential Medications Catalog
MEDICATION_CATALOG = [
    {"name": "Metformin", "category": "Antidiabetic", "form": "Tablet", "unit_cost": 0.25, "reorder": 500, "daily_dose": 1000},
    {"name": "Lisinopril", "category": "Antihypertensive", "form": "Tablet", "unit_cost": 0.35, "reorder": 400, "daily_dose": 20},
    {"name": "Atorvastatin", "category": "Statin", "form": "Tablet", "unit_cost": 0.45, "reorder": 600, "daily_dose": 40},
    {"name": "Amoxicillin", "category": "Antibiotic", "form": "Capsule", "unit_cost": 0.60, "reorder": 300, "daily_dose": 1500},
    {"name": "Furosemide", "category": "Diuretic", "form": "Tablet", "unit_cost": 0.20, "reorder": 350, "daily_dose": 40},
    {"name": "Amlodipine", "category": "Antihypertensive", "form": "Tablet", "unit_cost": 0.30, "reorder": 400, "daily_dose": 10},
    {"name": "Omeprazole", "category": "Proton Pump Inhibitor", "form": "Capsule", "unit_cost": 0.40, "reorder": 450, "daily_dose": 40},
    {"name": "Levothyroxine", "category": "Thyroid Hormone", "form": "Tablet", "unit_cost": 0.50, "reorder": 300, "daily_dose": 0.1},
    {"name": "Aspirin", "category": "Antiplatelet", "form": "Tablet", "unit_cost": 0.10, "reorder": 800, "daily_dose": 81},
    {"name": "Albuterol Inhaler", "category": "Bronchodilator", "form": "Inhaler", "unit_cost": 15.00, "reorder": 100, "daily_dose": 2},
    {"name": "Insulin Glargine", "category": "Antidiabetic", "form": "Vial", "unit_cost": 25.00, "reorder": 80, "daily_dose": 30},
    {"name": "Ceftriaxone", "category": "Antibiotic (IV)", "form": "Injection", "unit_cost": 8.50, "reorder": 120, "daily_dose": 2000},
]

# Departments
HOSPITAL_DEPARTMENTS = [
    "Cardiology",
    "Emergency Medicine",
    "Internal Medicine",
    "Oncology",
    "Orthopedics",
    "Pediatrics",
    "Pulmonology",
    "Neurology",
]
