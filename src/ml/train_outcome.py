"""
Model 6: 12-month outcome risk (population health), scored for every living patient as of today.

One gradient-boosting classifier per outcome: any hospital (inpatient) admission within 12 months,
and death within 12 months. Training uses a snapshot one year before the end of
the data, so every outcome is observed; features use only history recorded BEFORE that index date.
Scoring uses the same features computed as of the end of the data (gold_outcome_risk, snapshot
'score'). Each outcome is compared with an age-only baseline.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from sklearn.ensemble import HistGradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.evaluation import (  # noqa: E402
    baseline_auc,
    classification_report,
    cross_validated_auc,
    holdout_split,
    risk_band_thresholds,
    top_feature_importances,
)
from src.ml.features import OUTCOME_FEATURES, OUTCOMES, get_outcome_feature_matrix  # noqa: E402
from src.ml.model_registry import register_model  # noqa: E402
from src.utils.logging_utils import get_logger  # noqa: E402

logger = get_logger("train_outcome")

MIN_POSITIVES = 30


def train_outcome_risk_models() -> Dict[str, Any]:
    """Train one classifier per 12-month outcome and register them as a single artifact."""
    models, all_metrics = {}, {}
    for outcome, label in OUTCOMES.items():
        X, y, feature_cols = get_outcome_feature_matrix(outcome)
        if X.empty or int(y.sum()) < MIN_POSITIVES:
            logger.warning(f"Skipping {outcome}: too few positive events ({int(y.sum()) if len(y) else 0}).")
            continue

        # One row per patient, so a stratified split is already patient-disjoint
        train_idx, test_idx = holdout_split(X, y, groups=None)
        X_train, X_test, y_train, y_test = X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]

        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_depth=4, min_samples_leaf=40, l2_regularization=1.0,
            early_stopping=True, validation_fraction=0.15, random_state=42,
        )
        clf.fit(X_train, y_train)
        y_prob = clf.predict_proba(X_test)[:, 1]
        bands = risk_band_thresholds(y_prob)

        metrics = classification_report(y_test, y_prob, threshold=bands["high"])
        metrics.update(cross_validated_auc(clf, X, y, groups=None))
        metrics["baseline_roc_auc_age_only"] = baseline_auc(X_train, y_train, X_test, y_test, ["age_at_index"])
        metrics["positive_rate"] = round(float(y.mean()), 4)
        metrics["total_positives"] = int(y.sum())
        metrics["cohort_size"] = int(len(y))
        metrics["risk_bands"] = bands
        metrics["feature_importance"] = top_feature_importances(clf, feature_cols, X_test, y_test, k=6)
        metrics["label"] = label

        models[outcome] = {"model": clf, "risk_bands": bands, "label": label}
        all_metrics[outcome] = metrics
        logger.info(f"{outcome}: ROC-AUC {metrics['roc_auc']} (CV {metrics['cv_roc_auc_mean']}±{metrics['cv_roc_auc_std']}) "
                    f"vs age-only {metrics['baseline_roc_auc_age_only']} | prevalence {metrics['positive_rate']}")

    if not models:
        return {"status": "FAILED", "error": "No 12-month outcome had enough events to train"}

    artifact = {
        "models": models, "features": OUTCOME_FEATURES, "metrics": all_metrics, "version": "1.0.0",
        "trained_at": datetime.now().isoformat(), "type": "outcome_risk_classifiers",
    }
    path = register_model(model_name="outcome_risk_model", version="1.0.0", dataset="gold_outcome_risk", features=OUTCOME_FEATURES,
                          metrics=all_metrics, model_obj=artifact, filename="outcome_risk_model.joblib")
    return {"status": "SUCCESS", "model_name": "outcome_risk_model", "path": path, "metrics": all_metrics}


if __name__ == "__main__":
    train_outcome_risk_models()
