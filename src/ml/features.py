"""
Feature Engineering and Dataset Preparation for MediNexus AI ML Models.

All features come from Gold feature stores that are point-in-time correct:
- gold_patient_risk_features: one row per admission; history up to admission, stay facts known at discharge.
- gold_covid_outcomes: one row per patient; history strictly before the COVID-19 diagnosis date.
"""

from typing import Tuple, List, Optional
import pandas as pd
import numpy as np

from config.constants import GOLD_DATA_DIR
from src.utils.database import query_df

COMORBIDITY_FEATURES = [
    "has_hypertension", "has_diabetes", "has_copd", "has_heart_failure",
    "has_ckd", "has_cancer", "has_obesity",
]

# Predicting at discharge: the completed stay is known, nothing after discharge is.
READMISSION_FEATURES = [
    "age", "gender_encoded", "is_emergency", "is_urgent", "is_covid_admission",
    "length_of_stay_days", "is_icu", "mechanical_ventilation",
    "prior_admissions_365d", "prior_admissions_total",
    *COMORBIDITY_FEATURES,
    "total_diagnoses", "abnormal_lab_count", "critical_lab_count", "active_prescriptions_count",
]

# Predicting at admission: nothing about the stay itself is known yet.
LOS_BASE_FEATURES = [
    "age", "gender_encoded", "is_emergency", "is_urgent", "is_covid_admission",
    "prior_admissions_365d", "prior_admissions_total",
    *COMORBIDITY_FEATURES,
    "total_diagnoses", "active_prescriptions_count",
]

# Predicting at COVID-19 diagnosis: only pre-diagnosis history.
COVID_FEATURES = [
    "age_at_index", "gender_encoded",
    "has_hypertension", "has_diabetes", "has_prediabetes", "has_obesity", "has_heart_failure",
    "has_copd", "has_asthma", "has_ckd", "has_coronary_disease", "has_atrial_fibrillation",
    "has_stroke", "has_cancer", "has_dementia", "has_anemia",
    "comorbidity_count", "prior_admissions_5y", "active_medications",
    "last_bmi", "last_systolic_bp", "last_hba1c", "last_egfr",
]
COVID_OUTCOMES = {
    "hospitalized_30d": "Hospitalization within 30 days",
    "icu_30d": "ICU admission within 30 days",
    "ventilated_30d": "Mechanical ventilation within 30 days",
    "died_30d": "Death within 30 days",
}


def _load_gold(table: str) -> pd.DataFrame:
    parquet_path = GOLD_DATA_DIR / f"{table}.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    return query_df(f"SELECT * FROM {table}")


def load_risk_features() -> pd.DataFrame:
    """Load curated per-admission risk features from Gold layer."""
    return _load_gold("gold_patient_risk_features")


def load_covid_features() -> pd.DataFrame:
    """Load per-patient COVID-19 feature/outcome table from Gold layer."""
    return _load_gold("gold_covid_outcomes")


def _numeric_frame(df: pd.DataFrame, cols: List[str], fill: Optional[float] = 0.0) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in cols:
        values = pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)
        out[col] = values if fill is None else values.fillna(fill)
    return out


def get_readmission_feature_matrix() -> Tuple[pd.DataFrame, pd.Series, List[str], pd.Series]:
    """
    X, y, feature names and patient groups for UNPLANNED 30-day readmission.
    Excludes in-hospital deaths and admissions without a complete 30-day follow-up window.
    """
    df = load_risk_features()
    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=int), [], pd.Series(dtype=object)
    eligible = (pd.to_numeric(df["followup_complete"], errors="coerce") == 1) & (pd.to_numeric(df["died_in_hospital"], errors="coerce") == 0)
    df = df[eligible].reset_index(drop=True)
    X = _numeric_frame(df, READMISSION_FEATURES)
    y = pd.to_numeric(df["readmitted_30d"], errors="coerce").fillna(0).astype(int)
    return X, y, READMISSION_FEATURES, df["patient_id"]


def build_los_matrix(df: pd.DataFrame, feature_cols: Optional[List[str]] = None) -> Tuple[pd.DataFrame, List[str]]:
    """LOS features: admission-time facts plus one-hot admitting department."""
    X = _numeric_frame(df, LOS_BASE_FEATURES)
    dept = df.get("department_name", pd.Series("Unknown", index=df.index)).fillna("Unknown").astype(str)
    dummies = pd.get_dummies(dept, prefix="dept", dtype=int)
    X = pd.concat([X, dummies], axis=1)
    if feature_cols is not None:
        X = X.reindex(columns=feature_cols, fill_value=0)
    return X, list(X.columns)


def get_los_feature_matrix() -> Tuple[pd.DataFrame, pd.Series, List[str], pd.Series]:
    """X, y (observed length of stay in days), feature names and patient groups."""
    df = load_risk_features()
    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=float), [], pd.Series(dtype=object)
    X, feature_cols = build_los_matrix(df)
    y = pd.to_numeric(df["length_of_stay_days"], errors="coerce").fillna(1.0).astype(float)
    return X, y, feature_cols, df["patient_id"]


def get_covid_feature_matrix(outcome: str) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    X, y for one COVID-19 outcome among COVID-positive patients with a complete follow-up window.
    Missing vitals/labs are left as NaN (handled natively by the gradient-boosting model).
    """
    df = load_covid_features()
    if df.empty or outcome not in df.columns:
        return pd.DataFrame(), pd.Series(dtype=int), []
    cohort = (pd.to_numeric(df["covid_positive"], errors="coerce") == 1) & (pd.to_numeric(df["followup_complete"], errors="coerce") == 1)
    df = df[cohort].reset_index(drop=True)
    X = _numeric_frame(df, COVID_FEATURES, fill=None)
    y = pd.to_numeric(df[outcome], errors="coerce").fillna(0).astype(int)
    return X, y, COVID_FEATURES
