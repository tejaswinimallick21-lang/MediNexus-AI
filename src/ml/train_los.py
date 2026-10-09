"""
Model 2: Length of Stay (LOS) Regression Model (scored at admission).

Target: observed inpatient days from Synthea admit/discharge timestamps. Features are
admission-time facts only; the split is grouped by patient. MAE is reported against a
naive baseline that always predicts the training-set median stay.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.features import get_los_feature_matrix
from src.ml.evaluation import holdout_split, top_feature_importances
from src.ml.model_registry import register_model
from src.utils.logging_utils import get_logger

logger = get_logger("train_los")


def train_los_model() -> Dict[str, Any]:
    """
    Train and evaluate Length of Stay (LOS) regression model.
    """
    logger.info("Extracting Length of Stay features from Gold layer...")
    X, y, feature_cols, groups = get_los_feature_matrix()

    if X.empty or len(X) < 50:
        logger.warning("Insufficient data in Gold features matrix to train LOS model.")
        return {"status": "FAILED", "error": "Insufficient gold data"}

    train_idx, test_idx = holdout_split(X, y, groups)
    X_train, X_test, y_train, y_test = X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]

    # Absolute-error loss: stays are heavily right-skewed, so the median is the honest target
    reg = GradientBoostingRegressor(
        loss="absolute_error",
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
    )
    reg.fit(X_train, y_train)
    y_pred = np.clip(reg.predict(X_test), 0.0, 60.0)
    baseline_pred = np.full(len(y_test), float(y_train.median()))

    metrics = {
        "mae_days": round(float(mean_absolute_error(y_test, y_pred)), 3),
        "rmse_days": round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 3),
        "r2_score": round(float(r2_score(y_test, y_pred)), 3),
        "baseline_mae_days_median": round(float(mean_absolute_error(y_test, baseline_pred)), 3),
        "test_samples": int(len(y_test)),
        "mean_actual_los": round(float(y.mean()), 2),
        "median_actual_los": round(float(y.median()), 2),
        "split": "GroupShuffleSplit by patient_id (80/20)",
        "feature_importance": top_feature_importances(reg, feature_cols, X_test, y_test, k=6),
    }

    model_artifact = {
        "model": reg,
        "features": feature_cols,
        "metrics": metrics,
        "version": "2.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "los_regressor",
    }

    path = register_model(
        model_name="length_of_stay_model",
        version="2.0.0",
        dataset="gold_patient_risk_features",
        features=feature_cols,
        metrics=metrics,
        model_obj=model_artifact,
        filename="los_model.joblib",
    )

    logger.info(
        f"LOS model trained. MAE {metrics['mae_days']}d vs median-baseline {metrics['baseline_mae_days_median']}d, R2 {metrics['r2_score']}"
    )
    return {"status": "SUCCESS", "model_name": "length_of_stay_model", "path": path, "metrics": metrics}


if __name__ == "__main__":
    train_los_model()
