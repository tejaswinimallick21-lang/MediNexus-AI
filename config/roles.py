"""
Role-Based Access Control (RBAC) Definitions for MediNexus AI.
"""

from typing import Dict, List, Any

# Standard System Roles
ROLE_DATA_ENGINEER = "Data Engineer"
ROLE_DOCTOR = "Doctor"
ROLE_PHARMACIST = "Pharmacist"
ROLE_LAB_TECH = "Laboratory Technician"
ROLE_RECEPTIONIST = "Receptionist"
ROLE_HOSPITAL_ADMIN = "Hospital Administrator"
ROLE_IT_ADMIN = "IT Administrator"

ALL_ROLES = [
    ROLE_DATA_ENGINEER,
    ROLE_DOCTOR,
    ROLE_PHARMACIST,
    ROLE_LAB_TECH,
    ROLE_RECEPTIONIST,
    ROLE_HOSPITAL_ADMIN,
    ROLE_IT_ADMIN,
]

# Role Permissions Configuration
ROLE_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    ROLE_DATA_ENGINEER: {
        "title": "Lead Data & Analytics Engineer",
        "description": "Manages dataset generation, Medallion Bronze/Silver/Gold ingestion, quality validation, ML pipeline, and data monitoring.",
        "allowed_pages": ["welcome", "data_engineer", "it_admin"],
        "default_page": "data_engineer",
        "accessible_layers": ["raw", "bronze", "silver", "gold"],
        "accessible_tables": ["*"],
        "allowed_actions": [
            "generate_dataset",
            "upload_raw_data",
            "run_medallion_pipeline",
            "view_quality_reports",
            "train_ml_models",
            "view_model_registry",
            "view_system_logs",
        ],
        "allowed_agents": ["HealthAnalyst Agent"],
    },
    ROLE_DOCTOR: {
        "title": "Attending Physician / Specialist",
        "description": "Accesses patient clinical 360, diagnostic trends, lab outcomes, predictive readmission risks, and prescriptive clinical plans.",
        "allowed_pages": ["welcome", "doctor"],
        "default_page": "doctor",
        "accessible_layers": ["gold"],
        "accessible_tables": [
            "gold_patient_360",
            "gold_admissions",
            "gold_clinical",
            "gold_laboratory",
            "gold_prescriptions",
            "gold_patient_risk_features",
            "gold_covid_outcomes",
        ],
        "allowed_actions": [
            "search_patient",
            "view_patient_360",
            "predict_covid_outcomes",
            "predict_readmission",
            "predict_los",
            "view_clinical_prescriptions",
            "query_medicare_agent",
        ],
        "allowed_agents": ["MediCare Agent"],
    },
    ROLE_PHARMACIST: {
        "title": "Chief Clinical Pharmacist",
        "description": "Monitors drug inventory, stockout risks, prescription utilization, demand forecasts, and procurement recommendations.",
        "allowed_pages": ["welcome", "pharmacist"],
        "default_page": "pharmacist",
        "accessible_layers": ["gold"],
        "accessible_tables": [
            "gold_pharmacy",
            "gold_prescriptions",
            "gold_admissions",
        ],
        "allowed_actions": [
            "view_inventory",
            "view_low_stock",
            "forecast_drug_demand",
            "generate_procurement_order",
            "query_pharmalab_agent",
        ],
        "allowed_agents": ["PharmaLab Agent"],
    },
    ROLE_LAB_TECH: {
        "title": "Laboratory Operations Specialist",
        "description": "Tracks investigation throughput, critical abnormal result alerts, analyzer turnaround time, and staffing demand forecasts.",
        "allowed_pages": ["welcome", "laboratory"],
        "default_page": "laboratory",
        "accessible_layers": ["gold"],
        "accessible_tables": [
            "gold_laboratory",
            "gold_admissions",
        ],
        "allowed_actions": [
            "view_lab_workload",
            "view_abnormal_tests",
            "forecast_lab_workload",
            "view_analyzer_metrics",
            "query_pharmalab_agent",
        ],
        "allowed_agents": ["PharmaLab Agent"],
    },
    ROLE_RECEPTIONIST: {
        "title": "Front-Desk Patient Flow Coordinator",
        "description": "Manages appointment bookings, cancellations, check-in flow, and waiting times. Strictly restricted from clinical diagnoses and lab records.",
        "allowed_pages": ["welcome", "receptionist"],
        "default_page": "receptionist",
        "accessible_layers": ["gold"],
        "accessible_tables": [
            "gold_appointments",
        ],
        "allowed_actions": [
            "view_appointments",
            "search_appointment",
            "view_patient_flow",
            "view_waiting_times",
        ],
        "allowed_agents": [],
    },
    ROLE_HOSPITAL_ADMIN: {
        "title": "Executive Hospital Administrator",
        "description": "Enterprise-level operational intelligence: occupancy, revenue, readmission rates, resource surge forecasts, and capacity planning.",
        "allowed_pages": ["welcome", "administrator"],
        "default_page": "administrator",
        "accessible_layers": ["gold"],
        "accessible_tables": [
            "gold_hospital_operations",
            "gold_admissions",
            "gold_billing",
            "gold_appointments",
            "gold_pharmacy",
            "gold_laboratory",
            "gold_covid_outcomes",
        ],
        "allowed_actions": [
            "view_executive_kpis",
            "analyze_occupancy",
            "analyze_revenue",
            "forecast_resource_demand",
            "view_department_performance",
            "query_healthanalyst_agent",
        ],
        "allowed_agents": ["HealthAnalyst Agent"],
    },
    ROLE_IT_ADMIN: {
        "title": "Enterprise IT & Security Administrator",
        "description": "Monitors system health, database schemas, pipeline status, audit event streams, and security access logs.",
        "allowed_pages": ["welcome", "it_admin", "data_engineer"],
        "default_page": "it_admin",
        "accessible_layers": ["metadata", "gold", "silver", "bronze"],
        "accessible_tables": ["*"],
        "allowed_actions": [
            "view_pipeline_status",
            "view_audit_logs",
            "view_system_health",
            "view_database_stats",
            "export_audit_trail",
        ],
        "allowed_agents": ["HealthAnalyst Agent"],
    },
}

# Alias Laboratory Specialist to Laboratory Technician for UI consistency
ROLE_PERMISSIONS["Laboratory Specialist"] = ROLE_PERMISSIONS[ROLE_LAB_TECH]

