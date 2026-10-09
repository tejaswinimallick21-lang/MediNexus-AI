"""Analytics package for MediNexus AI."""
from src.analytics.metrics import (
    compute_executive_kpis,
    compute_doctor_kpis,
    compute_pharmacy_kpis,
    compute_lab_kpis,
    compute_reception_kpis,
)
from src.analytics.descriptive import (
    get_admissions_trend_chart,
    get_department_revenue_chart,
    get_risk_tier_donut_chart,
    get_patient_lab_timeline,
    get_pharmacy_stock_chart,
    get_lab_category_workload_chart,
    get_appointment_status_chart,
)
from src.analytics.diagnostic import diagnose_readmissions, diagnose_waiting_times
