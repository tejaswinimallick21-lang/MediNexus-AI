"""
Model 1: 12-month mortality risk for every living cancer patient, scored as of the end of the data.

A gradient-boosting classifier trained on a snapshot one year before the end of the data, so every
outcome is observed; features use only history recorded BEFORE that index date (cancer type and
stage, time since diagnosis, treatments received, tumour-marker status, labs, comorbidities).
Scoring uses the same features as of the end of the data (gold_outcome_risk, snapshot 'score').
It is compared with two baselines: age only, and stage + cancer type (what the chart already says),
so the report shows whether machine learning adds anything beyond staging.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.evaluation import (  # noqa: E402
    baseline_auc,
    classification_report,
    cross_validated_auc,
    holdout_split,
    risk_band_thresholds,
    top_feature_importances,
)
from src.ml.features import OUTCOME_FEATURES, OUTCOMES, STAGE_TYPE_BASELINE, get_outcome_feature_matrix  # noqa: E402
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
        metrics["baseline_roc_auc_stage_type"] = baseline_auc(X_train, y_train, X_test, y_test, STAGE_TYPE_BASELINE)
        metrics["positive_rate"] = round(float(y.mean()), 4)
        metrics["total_positives"] = int(y.sum())
        metrics["cohort_size"] = int(len(y))
        metrics["risk_bands"] = bands
        metrics["feature_importance"] = top_feature_importances(clf, feature_cols, X_test, y_test, k=6)
        metrics["label"] = label

        # Champion/challenger: serve the stage + type baseline when the model does not beat it
        fill = X_train[STAGE_TYPE_BASELINE].median()
        baseline = LogisticRegression(max_iter=1000).fit(X_train[STAGE_TYPE_BASELINE].fillna(fill), y_train)
        serving = "model" if metrics["roc_auc"] > metrics["baseline_roc_auc_stage_type"] else "stage_type_baseline"
        if serving == "stage_type_baseline":
            b_prob = baseline.predict_proba(X_test[STAGE_TYPE_BASELINE].fillna(fill))[:, 1]
            bands = risk_band_thresholds(b_prob)
            served = classification_report(y_test, b_prob, threshold=bands["high"])
        else:
            served = {k: metrics[k] for k in ("roc_auc", "precision", "recall", "test_positives")}
        metrics["serving_method"] = serving
        metrics["served_roc_auc"] = served["roc_auc"]
        metrics["served_precision"] = served["precision"]
        metrics["served_recall"] = served["recall"]
        metrics["risk_bands"] = bands

        models[outcome] = {"model": clf, "baseline_model": baseline, "baseline_features": STAGE_TYPE_BASELINE,
                           "baseline_fill": {k: float(v) for k, v in fill.items()}, "serving_method": serving,
                           "risk_bands": bands, "label": label}
        all_metrics[outcome] = metrics
        logger.info(f"{outcome}: ROC-AUC {metrics['roc_auc']} (CV {metrics['cv_roc_auc_mean']}±{metrics['cv_roc_auc_std']}) "
                    f"vs age-only {metrics['baseline_roc_auc_age_only']}, stage+type {metrics['baseline_roc_auc_stage_type']} "
                    f"| prevalence {metrics['positive_rate']}")

    if not models:
        return {"status": "FAILED", "error": "No 12-month outcome had enough events to train"}

    artifact = {
        "models": models, "features": OUTCOME_FEATURES, "metrics": all_metrics, "version": "1.0.0",
        "trained_at": datetime.now().isoformat(), "type": "mortality_risk_classifier",
    }
    path = register_model(model_name="outcome_risk_model", version="1.0.0", dataset="gold_outcome_risk", features=OUTCOME_FEATURES,
                          metrics=all_metrics, model_obj=artifact, filename="outcome_risk_model.joblib")
    return {"status": "SUCCESS", "model_name": "outcome_risk_model", "path": path, "metrics": all_metrics}


if __name__ == "__main__":
    train_outcome_risk_models()
