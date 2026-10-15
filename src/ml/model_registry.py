"""
Model Registry for MediNexus AI.
Manages metadata, versioning, performance tracking, and persistence of trained ML models in DuckDB.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import joblib

from config.constants import MODELS_DIR
from src.utils.database import execute_query, query_df
from src.utils.logging_utils import get_logger

logger = get_logger("model_registry")
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def register_model(
    model_name: str,
    version: str,
    dataset: str,
    features: List[str],
    metrics: Dict[str, Any],
    model_obj: Any,
    filename: str,
) -> str:
    """
    Save serialized model to disk and register in DuckDB model_registry table.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / filename
    joblib.dump(model_obj, model_path)

    training_time = datetime.now()
    features_json = json.dumps(features)
    metrics_json = json.dumps(metrics)

    # Deactivate existing active versions of the same model
    execute_query(
        "UPDATE model_registry SET status = 'SUPERSEDED' WHERE model_name = ? AND status = 'ACTIVE'",
        [model_name],
    )

    # Insert new record
    execute_query(
        """
        INSERT INTO model_registry (
            model_name, version, training_timestamp, dataset,
            features, metrics, model_path, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            model_name,
            version,
            training_time,
            dataset,
            features_json,
            metrics_json,
            str(model_path),
            "ACTIVE",
        ],
    )

    logger.info(f"Registered model {model_name} (v{version}) at {model_path}")
    return str(model_path)


def load_model(model_name: str) -> Optional[Any]:
    """
    Load active model from disk.
    """
    df = query_df(
        "SELECT model_path FROM model_registry WHERE model_name = ? AND status = 'ACTIVE' ORDER BY training_timestamp DESC LIMIT 1",
        [model_name],
    )
    if not df.empty:
        path_str = df.iloc[0]["model_path"]
        path = Path(path_str)
        if path.exists():
            return joblib.load(path)

    # Fallback to direct default file path
    filename_map = {
        "readmission_risk_model": "readmission_model.joblib",
        "length_of_stay_model": "los_model.joblib",
        "pharmacy_demand_model": "pharmacy_demand_model.joblib",
        "lab_workload_model": "lab_workload_model.joblib",
        "resource_demand_model": "resource_demand_model.joblib",
        "outcome_risk_model": "outcome_risk_model.joblib",
        "outpatient_demand_model": "outpatient_demand_model.joblib",
        "drug_class_demand_model": "drug_class_demand_model.joblib",
    }
    fallback_file = MODELS_DIR / filename_map.get(model_name, f"{model_name}.joblib")
    if fallback_file.exists():
        return joblib.load(fallback_file)

    return None


def get_model_registry_summary() -> pd.DataFrame:
    """Return summary dataframe of all registered models."""
    return query_df("SELECT * FROM model_registry ORDER BY training_timestamp DESC")
