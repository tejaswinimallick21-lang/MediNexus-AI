"""
Core Healthcare Mathematical Formulations and KPI Calculations for MediNexus AI.
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from src.utils.database import query_df


def compute_executive_kpis() -> Dict[str, Any]:
    """Calculate organization-wide executive healthcare KPIs."""
    df_adm = query_df("SELECT * FROM gold_admissions")
    df_bill = query_df("SELECT * FROM gold_billing")
    df_ops = query_df("SELECT * FROM gold_hospital_operations")

    if df_adm.empty:
        return {
            "total_patients": 0,
            "total_admissions": 0,
            "readmission_rate_pct": 0.0,
            "average_los_days": 0.0,
            "occupancy_rate_pct": 0.0,
            "total_revenue": 0.0,
            "collection_rate_pct": 0.0,
        }

    total_adm = len(df_adm)
    total_pts = df_adm["patient_id"].nunique()
    readm_count = int(df_adm["readmitted_30d"].sum()) if "readmitted_30d" in df_adm.columns else 0
    readm_rate = round((readm_count / max(1, total_adm)) * 100, 2)
    avg_los = round(float(df_adm["length_of_stay"].mean()), 1)

    total_rev = round(float(df_bill["total_amount"].sum()), 2) if not df_bill.empty else 0.0
    patient_due = round(float(df_bill["patient_payable"].sum()), 2) if not df_bill.empty else 0.0
    collected = total_rev - patient_due
    collection_rate = round((collected / max(1.0, total_rev)) * 100, 1)

    avg_occupancy = (
        round(float(df_ops["estimated_occupancy_rate"].mean() * 100), 1)
        if not df_ops.empty and "estimated_occupancy_rate" in df_ops.columns
        else 78.5
    )

    return {
        "total_patients": total_pts,
        "total_admissions": total_adm,
        "readmission_rate_pct": readm_rate,
        "average_los_days": avg_los,
        "occupancy_rate_pct": avg_occupancy,
        "total_revenue": total_rev,
        "collection_rate_pct": collection_rate,
    }


def compute_doctor_kpis(doctor_id: Optional[str] = None) -> Dict[str, Any]:
    """Calculate clinical KPIs for doctors."""
    where = f"WHERE doctor_id = '{doctor_id}'" if doctor_id else ""
    df_p = query_df("SELECT * FROM gold_patient_360")
    df_adm = query_df(f"SELECT * FROM gold_admissions {where}")

    high_risk_count = int((df_p["clinical_risk_tier"] == "High").sum()) if not df_p.empty else 0
    mod_risk_count = int((df_p["clinical_risk_tier"] == "Moderate").sum()) if not df_p.empty else 0

    return {
        "monitored_patients": len(df_p),
        "high_risk_patients": high_risk_count,
        "moderate_risk_patients": mod_risk_count,
        "active_admissions": len(df_adm),
        "doctor_readmission_rate": round(float(df_adm["readmitted_30d"].mean() * 100), 1) if not df_adm.empty else 0.0,
    }


def compute_pharmacy_kpis() -> Dict[str, Any]:
    """Calculate pharmacy inventory and utilization KPIs."""
    df_p = query_df("SELECT * FROM gold_pharmacy")
    df_rx = query_df("SELECT * FROM gold_prescriptions")

    if df_p.empty:
        return {"total_items": 0, "high_risk_items": 0, "total_dispensed": 0, "stockout_rate": 0.0}

    total_items = len(df_p)
    high_risk = int((df_p["stockout_risk"] == "High Risk").sum())
    mod_risk = int((df_p["stockout_risk"] == "Moderate Risk").sum())
    total_dispensed = int(df_p["total_dispensed_qty"].sum())

    return {
        "total_items": total_items,
        "high_risk_items": high_risk,
        "moderate_risk_items": mod_risk,
        "total_dispensed_units": total_dispensed,
        "active_prescriptions": len(df_rx),
    }


def compute_lab_kpis() -> Dict[str, Any]:
    """Calculate diagnostic laboratory workload KPIs."""
    df_lab = query_df("SELECT * FROM gold_laboratory")
    if df_lab.empty:
        return {"total_tests": 0, "abnormal_tests": 0, "critical_tests": 0, "abnormal_pct": 0.0}

    total_tests = len(df_lab)
    abnormal = int(df_lab["is_abnormal"].sum())
    critical = int(df_lab["is_critical"].sum())

    return {
        "total_tests": total_tests,
        "abnormal_tests": abnormal,
        "critical_tests": critical,
        "abnormal_pct": round((abnormal / max(1, total_tests)) * 100, 1),
        "critical_pct": round((critical / max(1, total_tests)) * 100, 1),
    }


def compute_reception_kpis() -> Dict[str, Any]:
    """Calculate front-desk reception, appointment, and wait time KPIs."""
    df_apt = query_df("SELECT * FROM gold_appointments")
    if df_apt.empty:
        return {"total_appointments": 0, "completed": 0, "no_shows": 0, "avg_wait_minutes": 0}

    total = len(df_apt)
    completed = int((df_apt["status"] == "Completed").sum())
    no_show = int((df_apt["status"] == "No-Show").sum())
    cancelled = int((df_apt["status"] == "Cancelled").sum())
    avg_wait = round(float(df_apt[df_apt["status"] == "Completed"]["waiting_time_minutes"].mean()), 1)

    return {
        "total_appointments": total,
        "completed": completed,
        "no_shows": no_show,
        "cancelled": cancelled,
        "no_show_rate_pct": round((no_show / max(1, total)) * 100, 1),
        "cancellation_rate_pct": round((cancelled / max(1, total)) * 100, 1),
        "avg_wait_minutes": avg_wait,
    }
