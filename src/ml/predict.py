"""
Inference Pipeline and Model Transparency Service for MediNexus AI.
Provides risk predictions, probability scoring, local factor attributions,
and mandatory regulatory clinical decision-support disclaimers.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np

from src.ml.model_registry import load_model
from src.utils.database import query_df

CLINICAL_DISCLAIMER = "AI/ML decision support - not a medical diagnosis. Intended exclusively for licensed healthcare provider reference."


def _latest_admission_features(patient_id: str) -> pd.DataFrame:
    """Most recent admission row for a patient from the point-in-time feature store."""
    return query_df(
        "SELECT * FROM gold_patient_risk_features WHERE patient_id = ? ORDER BY admission_date DESC LIMIT 1",
        [patient_id],
    )


def _risk_level(proba: float, bands: Dict[str, float]) -> str:
    """Cohort-relative risk band (thresholds learned from held-out predictions)."""
    if proba >= bands.get("high", 0.70):
        return "HIGH"
    if proba >= bands.get("moderate", 0.35):
        return "MODERATE"
    return "LOW"


def predict_patient_readmission(patient_id: str) -> Dict[str, Any]:
    """
    Predict unplanned 30-day readmission risk, scored on the patient's most recent admission
    as of its discharge. Risk bands are relative to the training cohort (top 10% = HIGH).
    """
    artifact = load_model("readmission_risk_model")
    if not artifact:
        return {
            "status": "UNAVAILABLE",
            "message": "Readmission risk model is not yet trained. Please train the model in the Data Engineering console.",
            "disclaimer": CLINICAL_DISCLAIMER,
        }

    clf = artifact["model"]
    feature_cols = artifact["features"]
    version = artifact.get("version", "1.0.0")
    bands = artifact.get("risk_bands", {})

    df_row = _latest_admission_features(patient_id)
    if df_row.empty:
        return {
            "status": "NOT_FOUND",
            "message": f"Patient {patient_id} has no inpatient admissions to score.",
            "risk_level": "N/A",
            "probability": 0.0,
            "contributing_factors": [],
            "disclaimer": CLINICAL_DISCLAIMER,
        }

    row = df_row.iloc[0]
    X_vec = df_row.reindex(columns=feature_cols).apply(pd.to_numeric, errors="coerce").fillna(0)
    proba = float(clf.predict_proba(X_vec)[0, 1])
    risk_level = _risk_level(proba, bands)
    base_rate = artifact.get("metrics", {}).get("positive_rate")

    # Observed factors on this admission (descriptive context, not model attributions)
    contributing_factors = []
    if row.get("has_cancer", 0) == 1:
        contributing_factors.append("Active oncology history")
    if float(row.get("length_of_stay_days", 0)) >= 7:
        contributing_factors.append(f"Prolonged index stay ({row.get('length_of_stay_days')} days)")
    if row.get("prior_admissions_365d", 0) >= 2:
        contributing_factors.append(f"Frequent admissions in the past year ({row.get('prior_admissions_365d')})")
    if row.get("is_icu", 0) == 1 or row.get("mechanical_ventilation", 0) == 1:
        contributing_factors.append("ICU care or mechanical ventilation during the stay")
    if row.get("critical_lab_count", 0) >= 1:
        contributing_factors.append(f"Critical lab results during the stay ({row.get('critical_lab_count')})")
    if row.get("has_heart_failure") == 1:
        contributing_factors.append("Congestive Heart Failure comorbidity")
    if row.get("has_copd") == 1:
        contributing_factors.append("Chronic Obstructive Pulmonary Disease burden")
    if row.get("age", 0) >= 65:
        contributing_factors.append(f"Advanced age ({row.get('age')} years at admission)")
    if not contributing_factors:
        contributing_factors = ["No major observed risk drivers on the most recent admission"]

    return {
        "status": "SUCCESS",
        "patient_id": patient_id,
        "admission_id": row.get("admission_id"),
        "admission_date": row.get("admission_date"),
        "prediction": "Elevated unplanned readmission risk" if risk_level == "HIGH" else "Not in the highest-risk decile",
        "risk_level": risk_level,
        "probability": round(proba * 100, 1),
        "cohort_base_rate_pct": round(base_rate * 100, 2) if base_rate is not None else None,
        "confidence": f"Holdout ROC-AUC {artifact.get('metrics', {}).get('roc_auc', 'n/a')}",
        "contributing_factors": contributing_factors[:4],
        "model_version": version,
        "timestamp": datetime.now().isoformat(),
        "disclaimer": CLINICAL_DISCLAIMER,
    }


def predict_patient_los(patient_id: str) -> Dict[str, Any]:
    """
    Predict expected length of stay (days) using admission-time facts of the patient's most recent admission.
    """
    artifact = load_model("length_of_stay_model")
    if not artifact:
        return {
            "status": "UNAVAILABLE",
            "message": "Length of stay model is not yet trained.",
            "disclaimer": CLINICAL_DISCLAIMER,
        }

    from src.ml.features import build_los_matrix

    reg = artifact["model"]
    feature_cols = artifact["features"]
    version = artifact.get("version", "1.0.0")

    df_row = _latest_admission_features(patient_id)
    if df_row.empty:
        return {"status": "NOT_FOUND", "message": f"Patient {patient_id} has no inpatient admissions to score.",
                "predicted_los_days": "N/A", "confidence_interval": "N/A", "disclaimer": CLINICAL_DISCLAIMER}

    X_vec, _ = build_los_matrix(df_row, feature_cols)
    pred_los = max(0.5, round(float(reg.predict(X_vec)[0]), 1))
    mae = artifact.get("metrics", {}).get("mae_days", 1.0)

    return {
        "status": "SUCCESS",
        "patient_id": patient_id,
        "admission_id": df_row.iloc[0].get("admission_id"),
        "predicted_los_days": pred_los,
        "observed_los_days": df_row.iloc[0].get("length_of_stay_days"),
        "confidence_interval": f"{max(0.5, pred_los - mae):.1f} - {pred_los + mae:.1f} days (± holdout MAE)",
        "model_version": version,
        "timestamp": datetime.now().isoformat(),
        "disclaimer": CLINICAL_DISCLAIMER,
    }


def predict_patient_covid_outcomes(patient_id: str) -> Dict[str, Any]:
    """
    Predict COVID-19 severe-outcome risks using only history recorded before diagnosis.
    For patients without a COVID-19 diagnosis, features are taken as of the end of the data
    ("if infected now"); for diagnosed patients, the observed outcomes are returned alongside.
    """
    artifact = load_model("covid_outcome_model")
    if not artifact:
        return {
            "status": "UNAVAILABLE",
            "message": "COVID-19 outcome model is not yet trained.",
            "disclaimer": CLINICAL_DISCLAIMER,
        }

    df_row = query_df("SELECT * FROM gold_covid_outcomes WHERE patient_id = ?", [patient_id])
    if df_row.empty:
        return {"status": "NOT_FOUND", "message": f"Patient {patient_id} is not in the COVID-19 risk cohort.",
                "outcomes": {}, "disclaimer": CLINICAL_DISCLAIMER}

    row = df_row.iloc[0]
    X_vec = df_row.reindex(columns=artifact["features"]).apply(pd.to_numeric, errors="coerce")
    covid_positive = int(row.get("covid_positive", 0)) == 1
    metrics = artifact.get("metrics", {})

    outcomes = {}
    for outcome, spec in artifact["models"].items():
        proba = float(spec["model"].predict_proba(X_vec)[0, 1])
        observed = row.get(outcome) if covid_positive else None
        outcomes[outcome] = {
            "label": spec["label"],
            "probability": round(proba * 100, 1),
            "risk_level": _risk_level(proba, spec["risk_bands"]),
            "cohort_rate_pct": round(metrics.get(outcome, {}).get("positive_rate", 0) * 100, 1),
            "observed": None if observed is None or pd.isna(observed) else int(observed),
        }

    drivers = []
    if row.get("age_at_index", 0) >= 65:
        drivers.append(f"Age {int(row.get('age_at_index'))} (the dominant risk factor in this cohort)")
    for flag, text in [("has_heart_failure", "Heart failure"), ("has_copd", "COPD"), ("has_ckd", "Chronic kidney disease"),
                       ("has_diabetes", "Type 2 diabetes"), ("has_obesity", "Obesity"), ("has_hypertension", "Hypertension"),
                       ("has_cancer", "Cancer history")]:
        if row.get(flag, 0) == 1:
            drivers.append(text)

    return {
        "status": "SUCCESS",
        "patient_id": patient_id,
        "covid_positive": covid_positive,
        "index_date": row.get("index_date"),
        "scored_as_of": "COVID-19 diagnosis date" if covid_positive else "end of observed data (hypothetical infection)",
        "outcomes": outcomes,
        "risk_drivers": drivers[:5] or ["No major pre-existing risk factors recorded"],
        "model_version": artifact.get("version", "1.0.0"),
        "timestamp": datetime.now().isoformat(),
        "disclaimer": CLINICAL_DISCLAIMER,
    }


def predict_drug_demand(medication_id: str) -> Dict[str, Any]:
    """
    Predict 30-Day Unit Demand for a medication.
    """
    artifact = load_model("pharmacy_demand_model")
    df_med = query_df("SELECT * FROM gold_pharmacy WHERE medication_id = ? LIMIT 1", [medication_id])

    if df_med.empty:
        return {"status": "NOT_FOUND", "message": f"Medication {medication_id} not found."}

    row = df_med.iloc[0]
    stock = float(row.get("stock_quantity", 100))
    daily_burn = float(row.get("estimated_daily_burn", 3.0))

    if artifact:
        reg = artifact["model"]
        feature_cols = artifact["features"]
        X_vec = pd.DataFrame([{
            "stock_quantity": stock,
            "reorder_level": float(row.get("reorder_level", 100)),
            "unit_cost": float(row.get("unit_cost", 0.50)),
            "estimated_daily_burn": daily_burn,
            "total_dispensed_qty": float(row.get("total_dispensed_qty", 200)),
        }])[feature_cols]
        predicted_30d_demand = int(round(float(reg.predict(X_vec)[0])))
    else:
        # Validated statistical fallback when ML not trained
        predicted_30d_demand = int(round(daily_burn * 30 * 1.15))

    shortfall = max(0, predicted_30d_demand - int(stock))

    return {
        "status": "SUCCESS",
        "medication_id": medication_id,
        "medication_name": row.get("medication_name", "Unknown"),
        "current_stock": int(stock),
        "predicted_30d_demand": predicted_30d_demand,
        "projected_shortfall": shortfall,
        "suggested_order_units": shortfall + int(row.get("reorder_level", 100)) if shortfall > 0 else 0,
        "timestamp": datetime.now().isoformat(),
    }
