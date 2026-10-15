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
        "SELECT * FROM gold_patient_risk_features WHERE patient_id = ? ORDER BY admission_date DESC, admission_id DESC LIMIT 1",
        [patient_id],
    )


def _risk_level(proba: float, bands: Dict[str, float]) -> str:
    """Cohort-relative risk band (thresholds learned from held-out predictions)."""
    if proba >= bands.get("high", 0.70):
        return "HIGH"
    if proba >= bands.get("moderate", 0.35):
        return "MODERATE"
    return "LOW"


def readmission_drivers(row) -> List[str]:
    """Observed risk factors on an admission row (descriptive context, not model attributions)."""
    def val(key, default=0):
        v = row.get(key, default) if hasattr(row, "get") else default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    factors = []
    if val("has_cancer") == 1:
        factors.append("Active oncology history")
    if val("length_of_stay_days") >= 7:
        factors.append(f"Prolonged index stay ({val('length_of_stay_days'):.1f} days)")
    if val("prior_admissions_365d") >= 2:
        factors.append(f"Frequent admissions in the past year ({int(val('prior_admissions_365d'))})")
    if val("is_icu") == 1 or val("mechanical_ventilation") == 1:
        factors.append("ICU care or mechanical ventilation during the stay")
    if val("critical_lab_count") >= 1:
        factors.append(f"Critical lab results during the stay ({int(val('critical_lab_count'))})")
    if val("has_heart_failure") == 1:
        factors.append("Congestive Heart Failure comorbidity")
    if val("has_copd") == 1:
        factors.append("Chronic Obstructive Pulmonary Disease burden")
    if val("age") >= 65:
        factors.append(f"Advanced age ({int(val('age'))} years at admission)")
    return factors or ["No major observed risk drivers on the most recent admission"]


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

    contributing_factors = readmission_drivers(row)

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


def predict_patient_outcome_risk(patient_id: str) -> Dict[str, Any]:
    """
    12-month outcome risks (unplanned admission, death) for a living patient, from history up to
    the end of the data. Trained one year earlier, when the outcomes are known.
    """
    artifact = load_model("outcome_risk_model")
    if not artifact:
        return {"status": "UNAVAILABLE", "message": "The 12-month outcome model is not yet trained.", "disclaimer": CLINICAL_DISCLAIMER}

    df_row = query_df("SELECT * FROM gold_outcome_risk WHERE patient_id = ? AND snapshot = 'score'", [patient_id])
    if df_row.empty:
        return {"status": "NOT_FOUND", "message": f"Patient {patient_id} is not in the living population scored today.",
                "outcomes": {}, "disclaimer": CLINICAL_DISCLAIMER}

    row = df_row.iloc[0]
    X_vec = df_row.reindex(columns=artifact["features"]).apply(pd.to_numeric, errors="coerce")
    metrics = artifact.get("metrics", {})
    outcomes = {}
    for outcome, spec in artifact["models"].items():
        proba = float(spec["model"].predict_proba(X_vec)[0, 1])
        outcomes[outcome] = {
            "label": spec["label"],
            "probability": round(proba * 100, 1),
            "risk_level": _risk_level(proba, spec["risk_bands"]),
            "cohort_rate_pct": round(metrics.get(outcome, {}).get("positive_rate", 0) * 100, 1),
            "observed": None,  # the next 12 months have not happened yet
        }

    drivers = []
    if row.get("age_at_index", 0) >= 65:
        drivers.append(f"Age {int(row.get('age_at_index'))}")
    if row.get("prior_admissions_5y", 0) >= 2:
        drivers.append(f"{int(row.get('prior_admissions_5y'))} admissions in the past 5 years")
    for flag, text in [("has_heart_failure", "Heart failure"), ("has_copd", "COPD"), ("has_ckd", "Chronic kidney disease"),
                       ("has_cancer", "Cancer history"), ("has_diabetes", "Type 2 diabetes"), ("has_dementia", "Dementia"),
                       ("has_stroke", "Previous stroke"), ("has_obesity", "Obesity"), ("has_hypertension", "Hypertension")]:
        if row.get(flag, 0) == 1:
            drivers.append(text)

    return {
        "status": "SUCCESS",
        "patient_id": patient_id,
        "index_date": row.get("index_date"),
        "scored_as_of": f"{row.get('index_date')} (today)",
        "outcomes": outcomes,
        "risk_drivers": drivers[:5] or ["No major pre-existing risk factors recorded"],
        "model_version": artifact.get("version", "1.0.0"),
        "timestamp": datetime.now().isoformat(),
        "disclaimer": CLINICAL_DISCLAIMER,
    }


METHOD_LABELS = {
    "model": "Gradient-boosting model",
    "surge_aware": "Surge-aware average",
    "baseline_naive7": "Naive baseline: last 7 days repeated",
    "baseline_last30": "Naive baseline: last 30 days repeated",
}


def _serving_note(artifact: Dict[str, Any]) -> Dict[str, Any]:
    m = artifact.get("metrics", {})
    method = artifact.get("serving_method", "model")
    return {
        "serving_method": method,
        "method_label": METHOD_LABELS.get(method, method),
        "holdout_mae": m.get("mae"),
        "holdout_baseline_mae": m.get("baseline_naive7_mae", m.get("baseline_last30_mae")),
        "holdout_surge_mae": m.get("surge_aware_mae"),
        "holdout_served_mae": m.get("served_mae"),
        "beats_baseline": m.get("beats_baseline"),
        "test_period": m.get("test_period"),
        "data_through": artifact.get("data_through"),
    }


def _daily_forecast(model_name: str, series_fn) -> Dict[str, Any]:
    from src.ml.forecasting import daily_supervised, predict_daily, surge_aware

    artifact = load_model(model_name)
    series, end = series_fn()
    latest = daily_supervised(series).sort_values("day").groupby("group").tail(1)
    method = artifact.get("serving_method") if artifact else None
    if method == "model":
        forecast = predict_daily(artifact["model"], latest)
    elif method == "surge_aware":
        forecast = surge_aware(latest["mean7"], latest["mean28"])
    else:  # champion/challenger chose the naive baseline (or no model yet)
        forecast = latest["mean7"].to_numpy()
    rows = [
        {
            "group": g,
            "forecast_daily": round(float(f), 1),
            "last_7d_daily": round(float(m7), 1),
            "last_28d_daily": round(float(m28), 1),
        }
        for g, f, m7, m28 in zip(latest["group"], forecast, latest["mean7"], latest["mean28"])
    ]
    return {
        "status": "SUCCESS",
        "horizon_days": 7,
        "as_of": str(end.date()),
        "forecasts": rows,
        **(_serving_note(artifact) if artifact else {"serving_method": "baseline_naive7", "method_label": "Naive baseline (model not trained)"}),
    }


def forecast_lab_workload() -> Dict[str, Any]:
    """Average daily tests per category for the next 7 days."""
    from src.ml.forecasting import lab_daily_series

    return _daily_forecast("lab_workload_model", lab_daily_series)


def forecast_outpatient_demand() -> Dict[str, Any]:
    """SIMULATED operations data: average daily outpatient demand per hospital for the next 7 days."""
    from src.ml.forecasting import outpatient_daily_series

    return _daily_forecast("outpatient_demand_model", outpatient_daily_series)


def forecast_drug_class_demand() -> Dict[str, Any]:
    """SIMULATED operations data: average daily units dispensed per drug class (network) for the next 7 days."""
    from src.ml.forecasting import pharmacy_class_series

    return _daily_forecast("drug_class_demand_model", pharmacy_class_series)


def forecast_admissions() -> Dict[str, Any]:
    """Average daily inpatient admissions across the network for the next 7 days."""
    from src.ml.forecasting import admissions_daily_series

    return _daily_forecast("resource_demand_model", admissions_daily_series)


def predict_drug_demand(medication_id: str, hospital_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Forecast 30-day unit demand for one stock line (site + medication). Without a hospital_id the
    lowest-stock site for that medication is used.
    """
    import pandas as pd
    from src.ml.forecasting import PHARMACY_FEATURES, pharmacy_frame

    where, params = "medication_id = ?", [medication_id]
    if hospital_id:
        where += " AND hospital_id = ?"
        params.append(hospital_id)
    df_med = query_df(f"SELECT * FROM gold_pharmacy WHERE {where} ORDER BY stock_quantity ASC LIMIT 1", params)
    if df_med.empty:
        return {"status": "NOT_FOUND", "message": f"Medication {medication_id} is not stocked{' at ' + hospital_id if hospital_id else ''}."}

    row = df_med.iloc[0]
    artifact = load_model("pharmacy_demand_model")
    end = pd.Timestamp(query_df("SELECT max(prescription_date) AS d FROM gold_prescriptions").iloc[0]["d"])
    pair = pd.DataFrame({"hospital_id": [row["hospital_id"]], "medication_id": [row["medication_id"]]})
    feats = pharmacy_frame([end], end, pairs=pair)
    if feats.empty:
        last30, predicted = 0.0, 0.0
    else:
        last30 = float(feats.iloc[0]["u30"])
        if artifact and artifact.get("serving_method") == "model":
            predicted = float(artifact["model"].predict(feats[PHARMACY_FEATURES])[0])
        else:
            predicted = last30
    predicted_units = int(round(max(0.0, predicted)))
    stock = int(float(row.get("stock_quantity", 0)))
    shortfall = max(0, predicted_units - stock)

    return {
        "status": "SUCCESS",
        "medication_id": medication_id,
        "hospital_id": row.get("hospital_id"),
        "hospital_name": row.get("hospital_name"),
        "medication_name": row.get("medication_name", "Unknown"),
        "current_stock": stock,
        "dispensed_last_30d": int(round(last30)),
        "predicted_30d_demand": predicted_units,
        "projected_shortfall": shortfall,
        "suggested_order_units": shortfall + int(float(row.get("reorder_level", 0))) if shortfall > 0 else 0,
        "timestamp": datetime.now().isoformat(),
        **(_serving_note(artifact) if artifact else {"serving_method": "baseline_last30", "method_label": "Naive baseline (model not trained)"}),
    }
