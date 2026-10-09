"""
Models 3, 4, 5: Operational & Resource Demand Forecasting Models.
Trains:
- Model 3: Pharmacy Medication Demand Regressor
- Model 4: Laboratory Workload Regressor
- Model 5: Hospital Bed / Admission Resource Demand Model
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import GOLD_DATA_DIR
from src.utils.database import query_df
from src.ml.model_registry import register_model
from src.utils.logging_utils import get_logger

logger = get_logger("train_demand")


def train_pharmacy_demand_model() -> Dict[str, Any]:
    """
    Train Model 3: 30-Day Medication Demand Forecasting.
    """
    logger.info("Training Pharmacy Demand Model from gold_pharmacy...")
    df_pharm = query_df("SELECT * FROM gold_pharmacy")
    if df_pharm.empty:
        return {"status": "FAILED", "error": "gold_pharmacy empty"}

    features = [
        "stock_quantity",
        "reorder_level",
        "unit_cost",
        "estimated_daily_burn",
        "total_dispensed_qty",
    ]

    for f in features:
        df_pharm[f] = pd.to_numeric(df_pharm[f], errors="coerce").fillna(10.0)

    # Historical demand target: 30 days projected demand
    y = (df_pharm["estimated_daily_burn"] * 30.0).round().clip(lower=5)
    X = df_pharm[features]

    reg = RandomForestRegressor(n_estimators=60, max_depth=6, random_state=42)
    reg.fit(X, y)

    y_pred = reg.predict(X)
    mae = round(float(mean_absolute_error(y, y_pred)), 2)
    r2 = round(float(r2_score(y, y_pred)), 3)

    metrics = {
        "mae_units": mae,
        "r2_score": r2,
        "sample_count": len(X),
    }

    model_artifact = {
        "model": reg,
        "features": features,
        "metrics": metrics,
        "version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "pharmacy_demand_forecaster",
    }

    path = register_model(
        model_name="pharmacy_demand_model",
        version="1.0.0",
        dataset="gold_pharmacy",
        features=features,
        metrics=metrics,
        model_obj=model_artifact,
        filename="pharmacy_demand_model.joblib",
    )

    logger.info(f"Pharmacy Demand Model trained. MAE: {mae} units, R2: {r2}")
    return {"status": "SUCCESS", "model_name": "pharmacy_demand_model", "path": path, "metrics": metrics}


def train_lab_workload_model() -> Dict[str, Any]:
    """
    Train Model 4: Laboratory Workload Volume Regressor.
    """
    logger.info("Training Laboratory Workload Model from gold_laboratory...")
    df_lab = query_df("""
        SELECT
            test_date,
            test_category,
            COUNT(*) as daily_volume,
            SUM(is_abnormal) as abnormal_tests,
            SUM(is_critical) as critical_tests
        FROM gold_laboratory
        GROUP BY test_date, test_category
    """)

    if df_lab.empty:
        return {"status": "FAILED", "error": "gold_laboratory empty"}

    df_lab["day_of_week"] = pd.to_datetime(df_lab["test_date"]).dt.dayofweek
    category_dummies = pd.get_dummies(df_lab["test_category"], drop_first=True, dtype=int)

    X = pd.concat([df_lab[["day_of_week", "abnormal_tests", "critical_tests"]], category_dummies], axis=1)
    y = df_lab["daily_volume"]

    features = list(X.columns)

    reg = RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
    reg.fit(X, y)

    y_pred = reg.predict(X)
    mae = round(float(mean_absolute_error(y, y_pred)), 2)

    metrics = {
        "mae_daily_tests": mae,
        "sample_count": len(X),
    }

    model_artifact = {
        "model": reg,
        "features": features,
        "metrics": metrics,
        "version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "lab_workload_forecaster",
    }

    path = register_model(
        model_name="lab_workload_model",
        version="1.0.0",
        dataset="gold_laboratory",
        features=features,
        metrics=metrics,
        model_obj=model_artifact,
        filename="lab_workload_model.joblib",
    )

    logger.info(f"Lab Workload Model trained. MAE: {mae} tests/day")
    return {"status": "SUCCESS", "model_name": "lab_workload_model", "path": path, "metrics": metrics}


def train_resource_demand_model() -> Dict[str, Any]:
    """
    Train Model 5: Hospital Resource & Bed Demand Forecaster.
    """
    logger.info("Training Resource Demand Model from gold_hospital_operations...")
    df_ops = query_df("SELECT * FROM gold_hospital_operations")
    if df_ops.empty:
        return {"status": "FAILED", "error": "gold_hospital_operations empty"}

    df_ops["day_of_week"] = pd.to_datetime(df_ops["admission_date"]).dt.dayofweek
    features = ["day_of_week", "emergency_admissions", "avg_stay_days"]

    X = df_ops[features].fillna(0)
    y = df_ops["daily_admissions"]

    reg = RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
    reg.fit(X, y)

    y_pred = reg.predict(X)
    mae = round(float(mean_absolute_error(y, y_pred)), 2)

    metrics = {
        "mae_daily_admissions": mae,
        "sample_count": len(X),
    }

    model_artifact = {
        "model": reg,
        "features": features,
        "metrics": metrics,
        "version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "resource_demand_forecaster",
    }

    path = register_model(
        model_name="resource_demand_model",
        version="1.0.0",
        dataset="gold_hospital_operations",
        features=features,
        metrics=metrics,
        model_obj=model_artifact,
        filename="resource_demand_model.joblib",
    )

    logger.info(f"Resource Demand Model trained. MAE: {mae} admissions/day")
    return {"status": "SUCCESS", "model_name": "resource_demand_model", "path": path, "metrics": metrics}


def train_all_models() -> Dict[str, Any]:
    """Train all 6 predictive models in sequence."""
    from src.ml.train_readmission import train_readmission_model
    from src.ml.train_los import train_los_model
    from src.ml.train_covid import train_covid_outcome_models

    r0 = train_covid_outcome_models()
    r1 = train_readmission_model()
    r2 = train_los_model()
    r3 = train_pharmacy_demand_model()
    r4 = train_lab_workload_model()
    r5 = train_resource_demand_model()

    return {
        "covid_outcomes": r0,
        "readmission": r1,
        "los": r2,
        "pharmacy_demand": r3,
        "lab_workload": r4,
        "resource_demand": r5,
    }


if __name__ == "__main__":
    train_all_models()
