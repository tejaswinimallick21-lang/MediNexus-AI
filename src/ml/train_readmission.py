"""
Model 1: Unplanned 30-Day Readmission Classifier (scored at discharge).

Label: unplanned readmission derived in Gold from admission dates (planned same-reason
repeat stays, transfers and in-hospital deaths excluded). Patient-grouped split, so no
patient appears in both train and test. Positives are rare in Synthea (~1-2%), so the
cross-validated AUC spread is reported alongside the holdout score.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from sklearn.ensemble import RandomForestClassifier

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.features import get_readmission_feature_matrix
from src.ml.evaluation import (
    holdout_split,
    cross_validated_auc,
    baseline_auc,
    classification_report,
    risk_band_thresholds,
    top_feature_importances,
)
from src.ml.model_registry import register_model
from src.utils.logging_utils import get_logger

logger = get_logger("train_readmission")

MIN_POSITIVES = 30


def train_readmission_model() -> Dict[str, Any]:
    """
    Train and evaluate the unplanned 30-day readmission classifier.
    """
    logger.info("Extracting readmission features from Gold layer...")
    X, y, feature_cols, groups = get_readmission_feature_matrix()

    if X.empty or int(y.sum()) < MIN_POSITIVES:
        logger.warning(f"Too few unplanned readmissions to train ({int(y.sum()) if len(y) else 0} < {MIN_POSITIVES}).")
        return {"status": "FAILED", "error": "Insufficient positive readmission events"}

    train_idx, test_idx = holdout_split(X, y, groups)
    X_train, X_test, y_train, y_test = X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]

    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=10,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    y_prob = clf.predict_proba(X_test)[:, 1]
    bands = risk_band_thresholds(y_prob)

    metrics = classification_report(y_test, y_prob, threshold=bands["high"])
    metrics.update(cross_validated_auc(clf, X, y, groups))
    metrics["baseline_roc_auc_age_los"] = baseline_auc(X_train, y_train, X_test, y_test, ["age", "length_of_stay_days"])
    metrics["positive_rate"] = round(float(y.mean()), 4)
    metrics["total_positives"] = int(y.sum())
    metrics["eligible_admissions"] = int(len(y))
    metrics["split"] = "GroupShuffleSplit by patient_id (80/20)"
    metrics["risk_bands"] = bands
    metrics["feature_importance"] = top_feature_importances(clf, feature_cols, X_test, y_test)

    model_artifact = {
        "model": clf,
        "features": feature_cols,
        "metrics": metrics,
        "risk_bands": bands,
        "version": "2.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "unplanned_readmission_classifier",
    }

    path = register_model(
        model_name="readmission_risk_model",
        version="2.0.0",
        dataset="gold_patient_risk_features",
        features=feature_cols,
        metrics=metrics,
        model_obj=model_artifact,
        filename="readmission_model.joblib",
    )

    logger.info(
        f"Readmission model trained. Holdout ROC-AUC {metrics['roc_auc']} | CV {metrics['cv_roc_auc_mean']}±{metrics['cv_roc_auc_std']} "
        f"| baseline {metrics['baseline_roc_auc_age_los']} | positives {metrics['total_positives']}"
    )
    return {"status": "SUCCESS", "model_name": "readmission_risk_model", "path": path, "metrics": metrics}


if __name__ == "__main__":
    train_readmission_model()
