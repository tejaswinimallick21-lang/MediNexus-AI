"""
Gold Medallion Layer for MediNexus AI.
Produces business-ready, AI-ready, and role-specific analytical data models:
- gold_patient_360
- gold_admissions
- gold_clinical
- gold_laboratory
- gold_pharmacy
- gold_prescriptions
- gold_appointments
- gold_billing
- gold_hospital_operations
- gold_patient_risk_features
- gold_outcome_risk (12-month mortality risk: train and score snapshots)
- gold_treatment_events (every surgery, chemotherapy / immunotherapy cycle, radiation session, hospice start)
- gold_oncology_patients (one row per cancer patient: type, stage, treatment pathway, tumour marker, survival)
- gold_survival (Kaplan-Meier survival by cancer type and stage)

Outcome labels are derived only from observed event dates (admissions, diagnoses, deaths).
ML features are computed strictly from information available at the prediction time.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import pandas as pd
import numpy as np
import duckdb

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import (
    SILVER_DATA_DIR,
    GOLD_DATA_DIR,
    OUTCOME_WINDOW_DAYS,
)
from src.utils.database import save_df_to_table, query_df
from src.utils.helpers import generate_uuid
from src.utils.logging_utils import get_logger

logger = get_logger("gold_transformation")

# ICD-10 prefixes used for comorbidity flags (patient 360, readmission and outcome-risk features)
COMORBIDITY_ICD10 = {
    "has_hypertension": ["I10"],
    "has_diabetes": ["E11"],
    "has_prediabetes": ["R73.0"],
    "has_obesity": ["E66"],
    "has_heart_failure": ["I50"],
    "has_copd": ["J43", "J44"],
    "has_asthma": ["J45"],
    "has_ckd": ["N18", "E11.2"],
    "has_coronary_disease": ["I25", "I21"],
    "has_atrial_fibrillation": ["I48"],
    "has_stroke": ["I63"],
    "has_cancer": ["C"],
    "has_dementia": ["G30"],
    "has_anemia": ["D64"],
}
CORE_COMORBIDITIES = ["has_hypertension", "has_diabetes", "has_copd", "has_heart_failure"]
OUTCOME_HORIZON_DAYS = 365  # 12-month outcome-risk window

# Oncology
CANCER_TYPES = ["Breast", "Prostate", "Lung", "Colon", "Melanoma", "Leukemia (CLL)", "Lymphoma (NHL)", "Pancreas"]
STAGE_NUM = {"I": 1, "II": 2, "III": 3, "IV": 4}
PRIMARY_MARKER = {  # the tumour marker followed for each cancer type
    "Breast": "CA 15-3", "Prostate": "PSA", "Lung": "CEA", "Colon": "CEA", "Pancreas": "CA 19-9",
    "Melanoma": "S-100", "Lymphoma (NHL)": "Lactate Dehydrogenase", "Leukemia (CLL)": "White Blood Cell Count",  # CLL: lymphocytosis
}
IMMUNOTHERAPY_REGIMENS = {"Pembrolizumab", "Nivolumab", "Ipilimumab + Nivolumab"}
TARGETED_REGIMENS = {"Ibrutinib"}
TREATMENT_TYPES = ["Surgery", "Chemotherapy", "Immunotherapy", "Targeted therapy", "Radiation"]
ACTIVE_TREATMENT_DAYS = 30
NEW_DIAGNOSIS_DAYS = 90  # untreated beyond this = watchful waiting, not awaiting treatment


def _type_column(cancer_type: str) -> str:
    """Feature column name for a cancer type (e.g. 'Leukemia (CLL)' -> 'type_leukemia')."""
    return "type_" + cancer_type.split(" ")[0].lower()


def kaplan_meier(durations_days: pd.Series, events: pd.Series, max_months: int = 120) -> pd.DataFrame:
    """Kaplan-Meier survival at each whole month (product-limit over daily event times)."""
    d = pd.DataFrame({"t": durations_days.clip(lower=0).to_numpy(), "e": events.astype(int).to_numpy()}).sort_values("t")
    n = len(d)
    surv, out, i = 1.0, [], 0
    deaths = d[d["e"] == 1].groupby("t").size()
    removed = d.groupby("t").size()
    at_risk = n
    times = removed.index.to_numpy()
    month_marks = {m: None for m in range(0, max_months + 1)}
    j = 0
    for m in range(0, max_months + 1):
        horizon = m * 30.4375
        while j < len(times) and times[j] <= horizon:
            t = times[j]
            dt = int(deaths.get(t, 0))
            if at_risk > 0 and dt:
                surv *= 1 - dt / at_risk
            at_risk -= int(removed[t])
            j += 1
        month_marks[m] = (surv, at_risk)
    for m, (sv, ar) in month_marks.items():
        out.append({"month": m, "survival_pct": round(sv * 100, 2), "at_risk": int(ar)})
    return pd.DataFrame(out)


def load_silver_table(table_name: str, silver_dir: Path = SILVER_DATA_DIR) -> pd.DataFrame:
    """Helper to load a silver parquet table."""
    path = silver_dir / f"{table_name}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    # Fallback to DuckDB silver table
    try:
        return query_df(f"SELECT * FROM silver_{table_name}")
    except Exception:
        return pd.DataFrame()


def _num(df: pd.DataFrame, col: str, default=0.0) -> pd.Series:
    """Numeric view of a (string-typed) silver column, with a default when absent."""
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _ts(df: pd.DataFrame, precise_col: str, date_col: str) -> pd.Series:
    """Prefer an exact timestamp column, falling back to the cleaned ISO date."""
    base = pd.to_datetime(df[date_col], errors="coerce") if date_col in df.columns else pd.Series(pd.NaT, index=df.index)
    if precise_col in df.columns:
        precise = pd.to_datetime(df[precise_col], errors="coerce")
        return precise.fillna(base)
    return base


def _comorbidity_condition(alias: str, flag: str) -> str:
    """SQL predicate matching a comorbidity flag's ICD-10 prefixes."""
    return " OR ".join(f"{alias}.icd10_code LIKE '{p}%'" for p in COMORBIDITY_ICD10[flag])


def derive_unplanned_readmissions(df_adm: pd.DataFrame, data_end: pd.Timestamp, window_days: int = OUTCOME_WINDOW_DAYS) -> pd.DataFrame:
    """
    Label each admission with whether an UNPLANNED readmission followed within `window_days`.

    - Next admission starting < 24h after discharge is treated as a transfer, not a readmission.
    - A readmission for the same reason that did not arrive via emergency is treated as planned
      (e.g. chemotherapy cycles, staged procedures) and excluded.
    - Admissions ending in death cannot be readmitted.
    - followup_complete marks admissions whose full window is inside the data (use for training).
    """
    df = df_adm.sort_values(["patient_id", "_adm_ts"]).copy()
    grp = df.groupby("patient_id", sort=False)
    df["_next_adm_ts"] = grp["_adm_ts"].shift(-1)
    df["_next_type"] = grp["admission_type"].shift(-1)
    df["_next_reason"] = grp["admission_reason"].shift(-1) if "admission_reason" in df.columns else np.nan

    gap = (df["_next_adm_ts"] - df["_dis_ts"]).dt.total_seconds() / 86400.0
    df["days_to_next_admission"] = gap.round(1)
    in_window = gap.between(1.0, window_days)
    same_reason = df["_next_reason"].notna() & (df["_next_reason"] == df.get("admission_reason"))
    planned = same_reason & (df["_next_type"] != "Emergency")
    died = df["discharge_disposition"].astype(str) == "Deceased"

    df["readmitted_30d_all_cause"] = (in_window & ~died).astype(int)
    df["readmitted_30d"] = (in_window & ~planned & ~died).astype(int)
    df["planned_readmission_30d"] = (in_window & planned & ~died).astype(int)
    df["followup_complete"] = ((df["_dis_ts"] + pd.Timedelta(days=window_days)) <= data_end).astype(int)
    return df.drop(columns=["_next_adm_ts", "_next_type", "_next_reason"])


def generate_gold_models(
    silver_dir: Path = SILVER_DATA_DIR,
    gold_dir: Path = GOLD_DATA_DIR,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Generate and persist all Gold analytical models.
    """
    run_id = run_id or generate_uuid("run_gld")
    gold_dir.mkdir(parents=True, exist_ok=True)
    created_models = {}
    created_at = datetime.now().isoformat()

    logger.info(f"Starting Gold Layer generation (Run ID: {run_id})")

    def persist(name: str, df: pd.DataFrame) -> None:
        df["_gold_created_at"] = created_at
        df.to_parquet(gold_dir / f"{name}.parquet", index=False)
        save_df_to_table(name, df, overwrite=True)
        created_models[name] = len(df)

    # Load required Silver datasets
    df_hospitals = load_silver_table("hospitals", silver_dir)
    df_departments = load_silver_table("departments", silver_dir)
    df_doctors = load_silver_table("doctors", silver_dir)
    df_patients = load_silver_table("patients", silver_dir)
    df_admissions = load_silver_table("admissions", silver_dir)
    df_diagnoses = load_silver_table("diagnoses", silver_dir)
    df_labs = load_silver_table("laboratory_results", silver_dir)
    df_meds = load_silver_table("medications", silver_dir)
    df_rx = load_silver_table("prescriptions", silver_dir)
    df_inv = load_silver_table("pharmacy_inventory", silver_dir)
    df_apts = load_silver_table("appointments", silver_dir)
    df_billing = load_silver_table("billing", silver_dir)

    # Join keys are text everywhere; an all-empty key column (e.g. no diagnosis made during a stay) loads as float
    for frame in (df_admissions, df_diagnoses, df_labs, df_rx, df_apts, df_billing):
        for key in ("admission_id", "encounter_id"):
            if key in frame.columns:
                frame[key] = frame[key].astype(object).where(frame[key].notna(), None)

    # Typed working copies
    df_patients["age"] = _num(df_patients, "age", 0).astype(int)
    df_patients["_dob"] = pd.to_datetime(df_patients.get("dob"), errors="coerce")
    df_patients["_death"] = pd.to_datetime(df_patients.get("death_date"), errors="coerce")
    for col in ["is_icu", "mechanical_ventilation"]:
        df_admissions[col] = _num(df_admissions, col, 0).astype(int)
    df_admissions["length_of_stay"] = _num(df_admissions, "length_of_stay", 1)
    df_admissions["_adm_ts"] = _ts(df_admissions, "admission_datetime", "admission_date")
    df_admissions["_dis_ts"] = _ts(df_admissions, "discharge_datetime", "discharge_date")
    if "length_of_stay_hours" in df_admissions.columns:
        df_admissions["length_of_stay_days"] = (_num(df_admissions, "length_of_stay_hours", 24) / 24.0).clip(0, 60).round(2)
    else:
        df_admissions["length_of_stay_days"] = df_admissions["length_of_stay"]

    if "admission_reason" not in df_admissions.columns:
        df_admissions["admission_reason"] = np.nan
    if "icd10_code" not in df_diagnoses.columns:
        df_diagnoses["icd10_code"] = np.nan

    date_candidates = [df_admissions["_dis_ts"].max(), pd.to_datetime(df_labs.get("test_date"), errors="coerce").max()]
    data_end = max(d for d in date_candidates if pd.notna(d)) if any(pd.notna(d) for d in date_candidates) else pd.Timestamp.now()
    logger.info(f"Gold reference date (end of observed data): {data_end.date()}")

    # Patient-level comorbidity sets (ever diagnosed) for Patient 360 views
    dx_valid = df_diagnoses[df_diagnoses["icd10_code"].notna() & df_diagnoses["patient_id"].notna()]
    flag_pids = {
        flag: set(dx_valid[dx_valid["icd10_code"].astype(str).str.startswith(tuple(prefixes))]["patient_id"])
        for flag, prefixes in COMORBIDITY_ICD10.items()
    }

    # -------------------------------------------------------------
    # 1. GOLD_ADMISSIONS (observed LOS; unplanned 30-day readmissions from admission dates)
    # -------------------------------------------------------------
    df_adm = derive_unplanned_readmissions(df_admissions, data_end)

    p_cols = ["patient_id"] + [c for c in ["name", "age", "gender", "blood_group", "insurance_provider"] if c in df_patients.columns]
    df_gold_admissions = df_adm.merge(df_patients[p_cols], on="patient_id", how="left").rename(columns={"name": "patient_name"})

    if "doctor_id" in df_gold_admissions.columns and "doctor_id" in df_doctors.columns:
        d_cols = ["doctor_id"] + [c for c in ["name", "specialty"] if c in df_doctors.columns]
        df_gold_admissions = df_gold_admissions.merge(df_doctors[d_cols], on="doctor_id", how="left")
        df_gold_admissions.rename(columns={"name": "attending_doctor", "specialty": "doctor_specialty"}, inplace=True)
    df_gold_admissions["attending_doctor"] = df_gold_admissions.get("attending_doctor", pd.Series(index=df_gold_admissions.index, dtype=object)).fillna("Unassigned")
    df_gold_admissions["doctor_specialty"] = df_gold_admissions.get("doctor_specialty", pd.Series(index=df_gold_admissions.index, dtype=object)).fillna("Unknown")

    if "department_name" not in df_gold_admissions.columns:
        if "department_id" in df_gold_admissions.columns and "department_id" in df_departments.columns:
            df_gold_admissions = df_gold_admissions.merge(df_departments[["department_id", "department_name"]], on="department_id", how="left")
        else:
            df_gold_admissions["department_name"] = "General Medicine"
    df_gold_admissions["department_name"] = df_gold_admissions["department_name"].fillna("Internal Medicine")

    if "hospital_id" in df_gold_admissions.columns and "hospital_id" in df_hospitals.columns:
        h_cols = ["hospital_id"] + [c for c in ["hospital_name", "location"] if c in df_hospitals.columns]
        df_gold_admissions = df_gold_admissions.merge(df_hospitals[h_cols], on="hospital_id", how="left")
    for col, default in [("hospital_name", "Unknown Facility"), ("location", "Unknown")]:
        if col not in df_gold_admissions.columns:
            df_gold_admissions[col] = default
        df_gold_admissions[col] = df_gold_admissions[col].fillna(default)

    if "admission_id" in df_billing.columns:
        b_cols = ["admission_id"] + [c for c in ["total_amount", "payment_status"] if c in df_billing.columns]
        df_gold_admissions = df_gold_admissions.merge(df_billing[b_cols], on="admission_id", how="left")
        df_gold_admissions.rename(columns={"total_amount": "billing_amount"}, inplace=True)
    df_gold_admissions["billing_amount"] = _num(df_gold_admissions, "billing_amount", 0.0)
    if "payment_status" not in df_gold_admissions.columns:
        df_gold_admissions["payment_status"] = "Unknown"

    df_gold_admissions["age"] = np.floor(
        (df_gold_admissions["_adm_ts"] - df_gold_admissions["patient_id"].map(df_patients.set_index("patient_id")["_dob"])).dt.days / 365.25
    ).fillna(df_gold_admissions.get("age", 0)).astype(int)
    df_gold_admissions = df_gold_admissions.drop(columns=["_adm_ts", "_dis_ts"])
    persist("gold_admissions", df_gold_admissions)
    adm_typed = df_adm  # keeps _adm_ts/_dis_ts for downstream temporal joins

    # -------------------------------------------------------------
    # 2. GOLD_CLINICAL
    # -------------------------------------------------------------
    adm_match_cols = ["admission_id"] + [c for c in ["patient_name", "admission_date", "discharge_date", "length_of_stay",
                                                     "admission_type", "department_name", "attending_doctor"]
                                         if c in df_gold_admissions.columns]
    df_gold_clinical = df_diagnoses.merge(df_gold_admissions[adm_match_cols], on="admission_id", how="left")
    pmini = df_patients[["patient_id"] + [c for c in ["name", "age", "gender"] if c in df_patients.columns]].rename(columns={"name": "_pname"})
    df_gold_clinical = df_gold_clinical.merge(pmini, on="patient_id", how="left")
    df_gold_clinical["patient_name"] = df_gold_clinical["patient_name"].fillna(df_gold_clinical["_pname"]) if "patient_name" in df_gold_clinical.columns else df_gold_clinical["_pname"]
    df_gold_clinical = df_gold_clinical.drop(columns=["_pname"])
    persist("gold_clinical", df_gold_clinical)

    # -------------------------------------------------------------
    # 3. GOLD_LABORATORY
    # -------------------------------------------------------------
    df_labs["test_value"] = _num(df_labs, "test_value", np.nan)
    df_gold_laboratory = df_labs.merge(pmini.rename(columns={"_pname": "patient_name"}), on="patient_id", how="left")
    if "admission_id" in df_gold_laboratory.columns:
        adm_lab_cols = ["admission_id"] + [c for c in ["department_name", "attending_doctor"] if c in df_gold_admissions.columns]
        df_gold_laboratory = df_gold_laboratory.merge(df_gold_admissions[adm_lab_cols], on="admission_id", how="left")
    flag = df_gold_laboratory.get("abnormal_flag", pd.Series("Normal", index=df_gold_laboratory.index))
    df_gold_laboratory["is_abnormal"] = flag.isin(["High", "Low", "Critical"]).astype(int)
    df_gold_laboratory["is_critical"] = (flag == "Critical").astype(int)
    persist("gold_laboratory", df_gold_laboratory)

    # -------------------------------------------------------------
    # 4. GOLD_PRESCRIPTIONS
    # -------------------------------------------------------------
    df_gold_prescriptions = df_rx.copy()
    if "medication_id" in df_gold_prescriptions.columns and "medication_id" in df_meds.columns:
        m_cols = ["medication_id"] + [c for c in ["medication_name", "category", "unit_cost"] if c in df_meds.columns]
        df_gold_prescriptions = df_gold_prescriptions.merge(df_meds[m_cols], on="medication_id", how="left")
        df_gold_prescriptions.rename(columns={"category": "medication_category"}, inplace=True)
    df_gold_prescriptions = df_gold_prescriptions.merge(pmini.rename(columns={"_pname": "patient_name"}), on="patient_id", how="left")
    if "total_cost" in df_gold_prescriptions.columns:
        df_gold_prescriptions["estimated_cost"] = _num(df_gold_prescriptions, "total_cost", 0.0).round(2)
    else:
        df_gold_prescriptions["estimated_cost"] = (_num(df_gold_prescriptions, "quantity", 30) * _num(df_gold_prescriptions, "unit_cost", 1.0)).round(2)
    persist("gold_prescriptions", df_gold_prescriptions)

    # -------------------------------------------------------------
    # 5. GOLD_PHARMACY (burn rate from the last 180 days of dispensing at each site)
    # -------------------------------------------------------------
    rx_dates = pd.to_datetime(df_rx.get("prescription_date"), errors="coerce")
    recent_rx = df_rx[rx_dates >= data_end - pd.Timedelta(days=180)].copy()
    recent_rx["quantity"] = _num(recent_rx, "quantity", 0)
    site_keys = [k for k in ["hospital_id", "medication_id"] if k in recent_rx.columns and k in df_inv.columns]
    rx_agg = recent_rx.groupby(site_keys).agg(
        total_dispensed_qty=("quantity", "sum"),
        prescription_count=("quantity", "count"),
    ).reset_index() if site_keys else pd.DataFrame(columns=["medication_id", "total_dispensed_qty", "prescription_count"])

    df_gold_pharmacy = df_inv.copy()
    df_gold_pharmacy["stock_quantity"] = _num(df_gold_pharmacy, "stock_quantity", 0)
    df_gold_pharmacy["reorder_level"] = _num(df_gold_pharmacy, "reorder_level", 0)
    if "medication_id" in df_meds.columns:
        m_ph_cols = ["medication_id"] + [c for c in ["medication_name", "category", "unit_cost", "reorder_threshold"] if c in df_meds.columns]
        df_gold_pharmacy = df_gold_pharmacy.merge(df_meds[m_ph_cols], on="medication_id", how="left")
    if "hospital_id" in df_gold_pharmacy.columns and "hospital_id" in df_hospitals.columns:
        df_gold_pharmacy = df_gold_pharmacy.merge(df_hospitals[["hospital_id", "hospital_name"]], on="hospital_id", how="left")
    df_gold_pharmacy = df_gold_pharmacy.merge(rx_agg, on=site_keys or ["medication_id"], how="left")
    df_gold_pharmacy["total_dispensed_qty"] = df_gold_pharmacy["total_dispensed_qty"].fillna(0)
    df_gold_pharmacy["prescription_count"] = df_gold_pharmacy["prescription_count"].fillna(0)
    df_gold_pharmacy["estimated_daily_burn"] = (df_gold_pharmacy["total_dispensed_qty"] / 180.0).round(3)
    df_gold_pharmacy["days_of_supply_remaining"] = np.where(
        df_gold_pharmacy["estimated_daily_burn"] > 0,
        (df_gold_pharmacy["stock_quantity"] / df_gold_pharmacy["estimated_daily_burn"].replace(0, np.nan)).round(1),
        999.0,
    )
    df_gold_pharmacy["stockout_risk"] = np.where(
        df_gold_pharmacy["stock_quantity"] <= df_gold_pharmacy["reorder_level"],
        "High Risk",
        np.where(df_gold_pharmacy["days_of_supply_remaining"] < 14, "Moderate Risk", "Safe"),
    )
    suggested_qty = np.where(
        df_gold_pharmacy["stockout_risk"] != "Safe",
        (df_gold_pharmacy["reorder_level"] * 2) - df_gold_pharmacy["stock_quantity"],
        0,
    )
    df_gold_pharmacy["suggested_reorder_qty"] = np.maximum(suggested_qty, 0)
    persist("gold_pharmacy", df_gold_pharmacy)

    # -------------------------------------------------------------
    # 6. GOLD_APPOINTMENTS
    # -------------------------------------------------------------
    df_gold_appointments = df_apts.merge(
        df_patients[["patient_id"] + [c for c in ["name", "age", "gender", "contact"] if c in df_patients.columns]].rename(columns={"name": "patient_name"}),
        on="patient_id", how="left",
    )
    if "doctor_id" in df_gold_appointments.columns and "doctor_id" in df_doctors.columns:
        d_apt_cols = ["doctor_id"] + [c for c in ["name", "specialty"] if c in df_doctors.columns]
        df_gold_appointments = df_gold_appointments.merge(df_doctors[d_apt_cols].rename(columns={"name": "doctor_name"}), on="doctor_id", how="left")
    if "department_id" in df_gold_appointments.columns and "department_id" in df_departments.columns:
        df_gold_appointments = df_gold_appointments.merge(df_departments[["department_id", "department_name"]], on="department_id", how="left")
    status_series = df_gold_appointments.get("status", pd.Series("Completed", index=df_gold_appointments.index))
    df_gold_appointments["is_completed"] = (status_series == "Completed").astype(int)
    df_gold_appointments["is_no_show"] = (status_series == "No-Show").astype(int)
    df_gold_appointments["is_cancelled"] = (status_series == "Cancelled").astype(int)
    persist("gold_appointments", df_gold_appointments)

    # -------------------------------------------------------------
    # 7. GOLD_BILLING
    # -------------------------------------------------------------
    adm_b_cols = ["admission_id"] + [c for c in ["patient_name", "admission_date", "discharge_date", "length_of_stay", "department_name", "hospital_name"] if c in df_gold_admissions.columns]
    df_gold_billing = df_billing.merge(df_gold_admissions[adm_b_cols], on="admission_id", how="left") if "admission_id" in df_billing.columns else df_billing.copy()
    tot = _num(df_gold_billing, "total_amount", 0.0)
    pat = _num(df_gold_billing, "patient_payable", 0.0)
    df_gold_billing["collection_rate"] = np.where(tot > 0, ((tot - pat) / tot).round(3), 1.0)
    persist("gold_billing", df_gold_billing)

    # -------------------------------------------------------------
    # 8. GOLD_PATIENT_360
    # -------------------------------------------------------------
    adm_agg = df_adm.groupby("patient_id").agg(
        total_admissions=("admission_id", "count"),
        total_los=("length_of_stay", "sum"),
        avg_los=("length_of_stay", "mean"),
        last_admission_date=("admission_date", "max"),
        prior_readmissions=("readmitted_30d", "sum"),
    ).reset_index()
    adm_agg["avg_los"] = adm_agg["avg_los"].round(1)

    chronic_dx = dx_valid[dx_valid["severity"].isin(["Moderate", "Severe"])] if "severity" in dx_valid.columns else dx_valid
    dx_agg = df_diagnoses.groupby("patient_id")["diagnosis_id"].count().reset_index(name="total_diagnoses")
    comorb_text = (
        chronic_dx.drop_duplicates(["patient_id", "diagnosis_description"])
        .groupby("patient_id")["diagnosis_description"]
        .apply(lambda s: "; ".join(s.head(6)))
        .reset_index(name="comorbidities_list")
    )
    dx_agg = dx_agg.merge(comorb_text, on="patient_id", how="left")

    lab_agg = df_gold_laboratory.groupby("patient_id").agg(
        total_lab_tests=("lab_id", "count"),
        abnormal_lab_count=("is_abnormal", "sum"),
        critical_lab_count=("is_critical", "sum"),
    ).reset_index()

    rx_status = df_rx.get("status", pd.Series("Active", index=df_rx.index))
    rx_patient_agg = df_rx.assign(_active=(rx_status == "Active").astype(int)).groupby("patient_id").agg(
        total_prescriptions=("prescription_id", "count"),
        active_prescriptions_count=("_active", "sum"),
    ).reset_index()

    bill_agg = df_billing.assign(
        _tot=_num(df_billing, "total_amount", 0.0), _pay=_num(df_billing, "patient_payable", 0.0)
    ).groupby("patient_id").agg(lifetime_billing=("_tot", "sum"), outstanding_due=("_pay", "sum")).reset_index()

    df_p360 = df_patients.drop(columns=["_dob", "_death"]).copy()
    for agg in [adm_agg, dx_agg, lab_agg, rx_patient_agg, bill_agg]:
        df_p360 = df_p360.merge(agg, on="patient_id", how="left")
    for flag_name in CORE_COMORBIDITIES + ["has_ckd", "has_cancer", "has_obesity"]:
        df_p360[flag_name] = df_p360["patient_id"].isin(flag_pids[flag_name]).astype(int)

    for col in ["total_admissions", "total_los", "prior_readmissions", "total_diagnoses", "total_lab_tests",
                "abnormal_lab_count", "critical_lab_count", "total_prescriptions", "active_prescriptions_count"]:
        df_p360[col] = df_p360[col].fillna(0).astype(int)
    df_p360["avg_los"] = df_p360["avg_los"].fillna(0.0)
    df_p360["comorbidities_list"] = df_p360["comorbidities_list"].fillna("None recorded")
    df_p360["lifetime_billing"] = df_p360["lifetime_billing"].fillna(0.0).round(2)
    df_p360["outstanding_due"] = df_p360["outstanding_due"].fillna(0.0).round(2)

    # Rule-based (not ML) oncology acuity tier for worklist triage: stage, age, aggressive tumour
    # types (lung, pancreas), comorbidity burden
    stage_num = df_p360.get("cancer_stage", pd.Series(index=df_p360.index, dtype=object)).map(STAGE_NUM).fillna(0)
    ctype = df_p360.get("cancer_type", pd.Series(index=df_p360.index, dtype=object)).fillna("")
    scores = (
        np.select([stage_num == 4, stage_num == 3, stage_num == 2], [4, 2, 1], 0) +
        np.where(df_p360["age"] >= 75, 2, np.where(df_p360["age"] >= 65, 1, 0)) +
        np.where(ctype.isin(["Lung", "Pancreas"]), 1, 0) +
        np.where(df_p360[CORE_COMORBIDITIES].sum(axis=1) >= 2, 1, 0)
    )
    df_p360["clinical_risk_tier"] = np.where(scores >= 5, "High", np.where(scores >= 3, "Moderate", "Low"))
    persist("gold_patient_360", df_p360)

    # -------------------------------------------------------------
    # 9. GOLD_HOSPITAL_OPERATIONS (observed midnight census vs estimated bed capacity)
    # -------------------------------------------------------------
    ops_src = df_gold_admissions[["admission_id", "admission_date", "hospital_id", "hospital_name", "department_name",
                                  "length_of_stay", "admission_type", "billing_amount"]].copy()
    ops_src["_start"] = pd.to_datetime(ops_src["admission_date"], errors="coerce")
    ops_src = ops_src.dropna(subset=["_start", "hospital_id"])
    stay_days = ops_src["length_of_stay"].clip(1, 60).astype(int)
    census = ops_src.loc[ops_src.index.repeat(stay_days), ["hospital_id", "hospital_name", "department_name", "_start"]].copy()
    census["_day"] = census["_start"] + pd.to_timedelta(census.groupby(level=0).cumcount(), unit="D")
    census_agg = census.groupby(["_day", "hospital_id", "hospital_name", "department_name"]).size().reset_index(name="inpatient_census")

    daily = ops_src.groupby(["_start", "hospital_id", "hospital_name", "department_name"]).agg(
        daily_admissions=("admission_id", "count"),
        avg_stay_days=("length_of_stay", "mean"),
        emergency_admissions=("admission_type", lambda s: (s == "Emergency").sum()),
        daily_billed_sum=("billing_amount", "sum"),
    ).reset_index().rename(columns={"_start": "_day"})

    ops = census_agg.merge(daily, on=["_day", "hospital_id", "hospital_name", "department_name"], how="left")
    for col in ["daily_admissions", "emergency_admissions", "daily_billed_sum", "avg_stay_days"]:
        ops[col] = ops[col].fillna(0)
    ops["avg_stay_days"] = ops["avg_stay_days"].round(1)
    ops["daily_billed_sum"] = ops["daily_billed_sum"].round(2)
    if {"hospital_id", "department_name", "bed_capacity"} <= set(df_departments.columns):
        cap = df_departments.assign(bed_capacity=_num(df_departments, "bed_capacity", 0))[["hospital_id", "department_name", "bed_capacity"]]
        ops = ops.merge(cap.drop_duplicates(["hospital_id", "department_name"]), on=["hospital_id", "department_name"], how="left")
    else:
        ops["bed_capacity"] = np.nan
    ops["estimated_occupancy_rate"] = np.where(
        ops["bed_capacity"] > 0, (ops["inpatient_census"] / ops["bed_capacity"]).round(3), np.nan
    )
    ops["admission_date"] = ops["_day"].dt.strftime("%Y-%m-%d")
    ops = ops.drop(columns=["_day"]).sort_values(["admission_date", "hospital_id"]).reset_index(drop=True)
    persist("gold_hospital_operations", ops)

    # -------------------------------------------------------------
    # 10. ONCOLOGY: treatment events, patient mart, survival
    # -------------------------------------------------------------
    hosp_names = df_hospitals.set_index("hospital_id")["hospital_name"] if "hospital_name" in df_hospitals.columns else pd.Series(dtype=object)
    cancer_pat = df_patients[df_patients.get("cancer_type", pd.Series(index=df_patients.index, dtype=object)).notna()].copy()
    cancer_pat["_dx"] = pd.to_datetime(cancer_pat.get("cancer_diagnosis_date"), errors="coerce")

    apt_done = df_apts[df_apts.get("status", pd.Series("Completed", index=df_apts.index)) == "Completed"].copy()
    apt_done["_d"] = pd.to_datetime(apt_done.get("appointment_date"), errors="coerce")
    etype = apt_done.get("encounter_type", pd.Series("", index=apt_done.index)).fillna("")
    chemo = apt_done[etype.str.startswith("Chemotherapy cycle")].copy()
    chemo["detail"] = chemo["encounter_type"].str.extract(r"\((.*)\)", expand=False)
    chemo["cycle"] = pd.to_numeric(chemo["encounter_type"].str.extract(r"cycle (\d+)", expand=False), errors="coerce")
    chemo["event_type"] = np.where(chemo["detail"].isin(IMMUNOTHERAPY_REGIMENS), "Immunotherapy",
                                   np.where(chemo["detail"].isin(TARGETED_REGIMENS), "Targeted therapy", "Chemotherapy"))
    radiation = apt_done[etype == "Encounter for radiation therapy"].assign(event_type="Radiation", detail="External beam radiation", cycle=np.nan)
    hospice = apt_done[etype == "Hospice care encounter"].assign(event_type="Hospice", detail="Hospice care", cycle=np.nan)
    surgery = df_admissions[df_admissions.get("surgery_procedure", pd.Series(index=df_admissions.index, dtype=object)).notna()].copy()
    surgery = surgery.assign(_d=surgery["_adm_ts"].dt.normalize(), event_type="Surgery", detail=surgery["surgery_procedure"], cycle=np.nan)
    ev_cols = ["patient_id", "_d", "event_type", "detail", "cycle", "hospital_id"]
    events = pd.concat([x[[c for c in ev_cols if c in x.columns]] for x in (chemo, radiation, hospice, surgery)], ignore_index=True)
    events = events.dropna(subset=["_d"]).merge(cancer_pat[["patient_id", "cancer_type", "cancer_stage"]], on="patient_id", how="inner")
    events["hospital_name"] = events["hospital_id"].map(hosp_names)
    events = events.sort_values(["_d", "patient_id", "event_type"]).reset_index(drop=True)
    df_events = events.assign(event_date=events["_d"].dt.strftime("%Y-%m-%d")).drop(columns=["_d"])
    persist("gold_treatment_events", df_events)

    treat = events[events["event_type"].isin(TREATMENT_TYPES)]
    first_tx = treat.sort_values("_d").groupby("patient_id").first()[["_d", "event_type"]].rename(columns={"_d": "_first_tx", "event_type": "first_treatment_type"})
    last_tx = treat.groupby("patient_id")["_d"].max().rename("_last_tx")
    counts = treat.pivot_table(index="patient_id", columns="event_type", values="_d", aggfunc="count", fill_value=0)
    counts = counts.reindex(columns=TREATMENT_TYPES, fill_value=0)
    regimen = (treat[treat["event_type"].isin(["Chemotherapy", "Immunotherapy", "Targeted therapy"])]
               .sort_values("_d").groupby("patient_id")["detail"].last().rename("systemic_regimen"))
    surg_first = surgery.sort_values("_d").groupby("patient_id").first()[["_d", "detail"]].rename(columns={"_d": "_surgery", "detail": "surgery_procedure"})
    hospice_start = hospice.groupby("patient_id")["_d"].min().rename("_hospice")
    last_visit = apt_done.groupby("patient_id")["_d"].max().rename("_last_visit")

    labs_t = df_gold_laboratory[["patient_id", "test_name", "test_value", "abnormal_flag", "test_date"]].assign(
        _t=pd.to_datetime(df_gold_laboratory["test_date"], errors="coerce"))
    marker_rows = cancer_pat[["patient_id", "cancer_type"]].assign(marker=cancer_pat["cancer_type"].map(PRIMARY_MARKER))
    mk = labs_t.merge(marker_rows, left_on=["patient_id", "test_name"], right_on=["patient_id", "marker"], how="inner").sort_values("_t")
    mk_last = mk.groupby("patient_id").tail(2).groupby("patient_id").agg(
        tumor_marker=("marker", "last"), marker_value=("test_value", "last"), marker_prev=("test_value", "first"),
        marker_flag=("abnormal_flag", "last"), _marker_date=("_t", "last"))

    onc = cancer_pat[["patient_id", "name", "gender", "age", "cancer_type", "cancer_stage", "_dob", "_death", "_dx",
                      "insurance_provider"]].copy() if "insurance_provider" in cancer_pat.columns else cancer_pat[
        ["patient_id", "name", "gender", "age", "cancer_type", "cancer_stage", "_dob", "_death", "_dx"]].copy()
    for frame in (first_tx, last_tx, counts, regimen, surg_first, hospice_start, last_visit, mk_last):
        onc = onc.merge(frame, left_on="patient_id", right_index=True, how="left")
    for col in TREATMENT_TYPES:
        onc[col] = onc[col].fillna(0).astype(int)
    onc = onc.rename(columns={"Surgery": "surgeries", "Chemotherapy": "chemo_cycles", "Immunotherapy": "immunotherapy_cycles",
                              "Targeted therapy": "targeted_therapy_cycles", "Radiation": "radiation_sessions"})
    onc["stage_num"] = onc["cancer_stage"].map(STAGE_NUM)
    onc["is_deceased"] = onc["_death"].notna().astype(int)
    onc["age_at_diagnosis"] = np.floor((onc["_dx"] - onc["_dob"]).dt.days / 365.25).astype("Int64")
    onc["survival_days"] = ((onc["_death"].fillna(data_end) - onc["_dx"]).dt.days).clip(lower=0)
    onc["days_to_treatment"] = (onc["_first_tx"] - onc["_dx"]).dt.days
    onc["days_since_last_treatment"] = (data_end - onc["_last_tx"]).dt.days
    active = (onc["days_since_last_treatment"] <= ACTIVE_TREATMENT_DAYS) & (onc["is_deceased"] == 0)
    untreated = onc["_first_tx"].isna()
    recent_dx = (data_end - onc["_dx"]).dt.days <= NEW_DIAGNOSIS_DAYS
    onc["treatment_status"] = np.select(
        [onc["is_deceased"] == 1, onc["_hospice"].notna(), active, untreated & recent_dx, untreated],
        ["Deceased", "Hospice", "In treatment", "Awaiting treatment", "Watchful waiting"], "Surveillance")
    onc["marker_trend"] = np.select(
        [onc["marker_value"] > onc["marker_prev"] * 1.1, onc["marker_value"] < onc["marker_prev"] * 0.9],
        ["Rising", "Falling"], np.where(onc["marker_value"].notna(), "Stable", None))
    for c, src in [("diagnosis_date", "_dx"), ("death_date", "_death"), ("first_treatment_date", "_first_tx"),
                   ("last_treatment_date", "_last_tx"), ("surgery_date", "_surgery"), ("hospice_start_date", "_hospice"),
                   ("last_visit_date", "_last_visit"), ("marker_date", "_marker_date")]:
        onc[c] = onc[src].dt.strftime("%Y-%m-%d")
    onc = onc.drop(columns=["_dob", "_death", "_dx", "_first_tx", "_last_tx", "_surgery", "_hospice", "_last_visit", "_marker_date", "marker_prev"])
    persist("gold_oncology_patients", onc)

    surv_rows = []
    groups = [("All patients", "all", onc)] + [(t, "cancer_type", onc[onc["cancer_type"] == t]) for t in CANCER_TYPES] + \
             [(f"Stage {s}", "stage", onc[onc["cancer_stage"] == s]) for s in STAGE_NUM]
    for label, kind, g in groups:
        if len(g) < 20:
            continue
        km = kaplan_meier(g["survival_days"], g["is_deceased"]).assign(group_type=kind, group_label=label, patients=len(g))
        surv_rows.append(km)
    for t in CANCER_TYPES:  # type x stage, for the stage-specific survival table
        for st in STAGE_NUM:
            g = onc[(onc["cancer_type"] == t) & (onc["cancer_stage"] == st)]
            if len(g) >= 20:
                surv_rows.append(kaplan_meier(g["survival_days"], g["is_deceased"]).assign(
                    group_type="type_stage", group_label=f"{t} | Stage {st}", patients=len(g)))
    persist("gold_survival", pd.concat(surv_rows, ignore_index=True))

    # -------------------------------------------------------------
    # 11 & 12. ML FEATURE STORES (point-in-time correct, computed in DuckDB)
    # -------------------------------------------------------------
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    con.register("adm", adm_typed[["admission_id", "patient_id", "_adm_ts", "_dis_ts", "admission_type", "admission_reason",
                                   "department_name", "discharge_disposition", "length_of_stay", "length_of_stay_days",
                                   "is_icu", "mechanical_ventilation", "readmitted_30d", "readmitted_30d_all_cause",
                                   "planned_readmission_30d", "followup_complete"]])
    con.register("pat", df_patients[["patient_id", "gender", "_dob", "_death"]])
    con.register("onc", cancer_pat[["patient_id", "cancer_type", "cancer_stage", "_dx"]].assign(
        stage_num=cancer_pat["cancer_stage"].map(STAGE_NUM)))
    con.register("tx", events[events["event_type"].isin(TREATMENT_TYPES)][["patient_id", "_d", "event_type"]])
    con.register("marker", mk[["patient_id", "_t", "abnormal_flag"]] if len(mk) else
                 pd.DataFrame({"patient_id": pd.Series(dtype=str), "_t": pd.Series(dtype="datetime64[ns]"), "abnormal_flag": pd.Series(dtype=str)}))
    dx_frame = df_diagnoses[["patient_id", "icd10_code"]].assign(_dx_date=pd.to_datetime(df_diagnoses["diagnosis_date"], errors="coerce"))
    con.register("dx", dx_frame)
    con.register("labs", df_gold_laboratory[["patient_id", "admission_id", "test_name", "test_value", "is_abnormal", "is_critical"]]
                 .assign(_t=pd.to_datetime(df_gold_laboratory["test_date"], errors="coerce")))
    rx_end = pd.to_datetime(df_rx.get("end_date"), errors="coerce") if "end_date" in df_rx.columns else pd.Series(pd.NaT, index=df_rx.index)
    con.register("rx", pd.DataFrame({"patient_id": df_rx["patient_id"], "_start": rx_dates, "_end": rx_end}))

    flag_sql = ",\n".join(
        f"max(CASE WHEN ({_comorbidity_condition('d', f)}) THEN 1 ELSE 0 END) AS {f}" for f in COMORBIDITY_ICD10
    )

    # 10. Readmission / LOS features: history up to discharge, stay facts known at discharge
    df_features = con.execute(f"""
        WITH comorb AS (
            SELECT a.admission_id, {flag_sql}, count(DISTINCT d.icd10_code) AS total_diagnoses
            FROM adm a LEFT JOIN dx d ON d.patient_id = a.patient_id AND d._dx_date <= a._adm_ts
            GROUP BY a.admission_id),
        prior AS (
            SELECT a.admission_id,
                   count(p.admission_id) FILTER (WHERE p._adm_ts >= a._adm_ts - INTERVAL 365 DAY) AS prior_admissions_365d,
                   count(p.admission_id) AS prior_admissions_total,
                   coalesce(sum(p.length_of_stay), 0) AS prior_total_los
            FROM adm a LEFT JOIN adm p ON p.patient_id = a.patient_id AND p._adm_ts < a._adm_ts
            GROUP BY a.admission_id),
        stay_labs AS (
            SELECT admission_id, sum(is_abnormal) AS abnormal_lab_count, sum(is_critical) AS critical_lab_count
            FROM labs WHERE admission_id IS NOT NULL GROUP BY admission_id),
        meds AS (
            SELECT a.admission_id, count(r._start) AS active_prescriptions_count
            FROM adm a LEFT JOIN rx r ON r.patient_id = a.patient_id AND r._start <= a._adm_ts
                 AND (r._end IS NULL OR r._end >= a._adm_ts)
            GROUP BY a.admission_id)
        SELECT a.admission_id, a.patient_id,
               CAST(floor(date_diff('day', p._dob, a._adm_ts) / 365.25) AS INTEGER) AS age,
               p.gender, a.admission_type, a.admission_reason, a.department_name,
               CASE WHEN p.gender = 'Male' THEN 1 ELSE 0 END AS gender_encoded,
               CASE WHEN a.admission_type = 'Emergency' THEN 1 ELSE 0 END AS is_emergency,
               CASE WHEN a.admission_type = 'Urgent' THEN 1 ELSE 0 END AS is_urgent,
               a.length_of_stay, a.length_of_stay_days, a.is_icu, a.mechanical_ventilation,
               pr.prior_admissions_365d, pr.prior_admissions_total,
               pr.prior_admissions_total + 1 AS total_admissions,
               pr.prior_total_los + a.length_of_stay AS total_los,
               round((pr.prior_total_los + a.length_of_stay) / (pr.prior_admissions_total + 1), 1) AS avg_los,
               c.* EXCLUDE (admission_id),
               coalesce(l.abnormal_lab_count, 0) AS abnormal_lab_count,
               coalesce(l.critical_lab_count, 0) AS critical_lab_count,
               m.active_prescriptions_count,
               CASE WHEN a.discharge_disposition = 'Deceased' THEN 1 ELSE 0 END AS died_in_hospital,
               a.readmitted_30d, a.readmitted_30d_all_cause, a.planned_readmission_30d, a.followup_complete,
               strftime(a._adm_ts, '%Y-%m-%d') AS admission_date
        FROM adm a
        JOIN pat p USING (patient_id)
        LEFT JOIN comorb c ON c.admission_id = a.admission_id
        LEFT JOIN prior pr ON pr.admission_id = a.admission_id
        LEFT JOIN stay_labs l ON l.admission_id = a.admission_id
        LEFT JOIN meds m ON m.admission_id = a.admission_id
        ORDER BY a._adm_ts
    """).df()
    persist("gold_patient_risk_features", df_features)

    # 12. 12-month mortality risk: two snapshots of every living cancer patient diagnosed before the
    #     index date, features strictly before it.
    #     train: index = one year before the end of the data, deaths observed over the following 365 days.
    #     score: index = end of the data; outcomes not yet known.
    #     Emergency and hospice visits are NOT features: in this synthetic data they occur only in the
    #     last weeks before death, so they would leak the outcome.
    def outcome_snapshot(index_ts: pd.Timestamp, snapshot: str):
        idx = index_ts.strftime("%Y-%m-%d %H:%M:%S")
        labelled = snapshot == "train"
        return con.execute(f"""
        WITH cohort AS (
            SELECT p.patient_id, p.gender, p._dob, p._death, TIMESTAMP '{idx}' AS index_date,
                   o.cancer_type, o.stage_num, o._dx
            FROM pat p JOIN onc o USING (patient_id)
            WHERE o._dx < TIMESTAMP '{idx}' AND (p._death IS NULL OR p._death > TIMESTAMP '{idx}')),
        treatment AS (
            SELECT c.patient_id,
                   count(t._d) FILTER (WHERE t.event_type = 'Surgery') AS surgeries_before,
                   count(t._d) FILTER (WHERE t.event_type = 'Chemotherapy') AS chemo_cycles_before,
                   count(t._d) FILTER (WHERE t.event_type IN ('Immunotherapy', 'Targeted therapy')) AS immuno_targeted_cycles_before,
                   count(t._d) FILTER (WHERE t.event_type = 'Radiation') AS radiation_sessions_before,
                   count(t._d) FILTER (WHERE t._d >= c.index_date - INTERVAL 90 DAY) AS treatments_last_90d
            FROM cohort c LEFT JOIN tx t ON t.patient_id = c.patient_id AND t._d < c.index_date
            GROUP BY c.patient_id),
        markers AS (
            SELECT c.patient_id,
                   arg_max(CASE WHEN m.abnormal_flag IN ('High', 'Critical') THEN 1 ELSE 0 END, m._t) AS marker_elevated,
                   avg(CASE WHEN m.abnormal_flag IN ('High', 'Critical') THEN 1.0 ELSE 0.0 END) AS marker_elevated_share
            FROM cohort c LEFT JOIN marker m ON m.patient_id = c.patient_id AND m._t < c.index_date
            GROUP BY c.patient_id),
        comorb AS (
            SELECT c.patient_id, {flag_sql}
            FROM cohort c LEFT JOIN dx d ON d.patient_id = c.patient_id AND d._dx_date < c.index_date
            GROUP BY c.patient_id),
        hist AS (
            SELECT c.patient_id,
                   count(a.admission_id) FILTER (WHERE a._adm_ts >= c.index_date - INTERVAL 1825 DAY AND a._adm_ts < c.index_date) AS prior_admissions_5y
            FROM cohort c LEFT JOIN adm a ON a.patient_id = c.patient_id GROUP BY c.patient_id),
        meds AS (
            SELECT c.patient_id, count(r._start) AS active_medications
            FROM cohort c LEFT JOIN rx r ON r.patient_id = c.patient_id AND r._start < c.index_date
                 AND (r._end IS NULL OR r._end >= c.index_date)
            GROUP BY c.patient_id),
        vitals AS (
            SELECT c.patient_id,
                   arg_max(l.test_value, l._t) FILTER (WHERE l.test_name = 'Body Mass Index') AS last_bmi,
                   arg_max(l.test_value, l._t) FILTER (WHERE l.test_name = 'Hemoglobin') AS last_hemoglobin,
                   arg_max(l.test_value, l._t) FILTER (WHERE l.test_name = 'Lactate Dehydrogenase') AS last_ldh,
                   arg_max(l.test_value, l._t) FILTER (WHERE l.test_name = 'Creatinine') AS last_creatinine
            FROM cohort c LEFT JOIN labs l ON l.patient_id = c.patient_id AND l._t < c.index_date
            GROUP BY c.patient_id)
        SELECT '{snapshot}' AS snapshot, c.patient_id, strftime(c.index_date, '%Y-%m-%d') AS index_date,
               CAST(floor(date_diff('day', c._dob, c.index_date) / 365.25) AS INTEGER) AS age_at_index,
               CASE WHEN c.gender = 'Male' THEN 1 ELSE 0 END AS gender_encoded,
               cm.* EXCLUDE (patient_id),
               {' + '.join(f'cm.{f}' for f in COMORBIDITY_ICD10 if f != 'has_cancer')} AS comorbidity_count,
               c.cancer_type, c.stage_num,
               {', '.join(f"CASE WHEN c.cancer_type = '{t}' THEN 1 ELSE 0 END AS {_type_column(t)}" for t in CANCER_TYPES)},
               CAST(floor(date_diff('day', c._dx, c.index_date) / 30.4375) AS INTEGER) AS months_since_diagnosis,
               CAST(floor(date_diff('day', c._dob, c._dx) / 365.25) AS INTEGER) AS age_at_diagnosis,
               tr.surgeries_before, tr.chemo_cycles_before, tr.immuno_targeted_cycles_before,
               tr.radiation_sessions_before, tr.treatments_last_90d,
               coalesce(mk.marker_elevated, 0) AS marker_elevated, coalesce(mk.marker_elevated_share, 0) AS marker_elevated_share,
               h.prior_admissions_5y, m.active_medications,
               v.last_bmi, v.last_hemoglobin, v.last_ldh, v.last_creatinine,
               {f"CASE WHEN c._death > c.index_date AND c._death <= c.index_date + INTERVAL {OUTCOME_HORIZON_DAYS} DAY THEN 1 ELSE 0 END" if labelled else 'NULL'} AS died_12m
        FROM cohort c
        JOIN comorb cm USING (patient_id)
        JOIN hist h USING (patient_id)
        JOIN meds m USING (patient_id)
        JOIN vitals v USING (patient_id)
        JOIN treatment tr USING (patient_id)
        JOIN markers mk USING (patient_id)
        ORDER BY c.patient_id
        """).df()

    df_outcomes = pd.concat([
        outcome_snapshot(data_end - pd.Timedelta(days=OUTCOME_HORIZON_DAYS), "train"),
        outcome_snapshot(data_end, "score"),
    ], ignore_index=True)
    con.close()
    persist("gold_outcome_risk", df_outcomes)

    logger.info(f"Gold Layer Generation Complete. Models created: {list(created_models.keys())}")

    return {
        "run_id": run_id,
        "status": "SUCCESS",
        "models": created_models,
        "total_gold_tables": len(created_models),
        "data_through": str(data_end.date()),
        "generated_at": datetime.now().isoformat(),
    }
