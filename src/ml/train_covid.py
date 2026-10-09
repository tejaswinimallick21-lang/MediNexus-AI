"""
Model 6: COVID-19 Severe Outcome Risk (scored at the time of COVID-19 diagnosis).

One gradient-boosting classifier per outcome (hospitalization, ICU, ventilation, death within
30 days). Features use only history recorded BEFORE the diagnosis date, so nothing from the
COVID episode itself (in-hospital labs, ICU stay) can leak into the prediction.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from sklearn.ensemble import HistGradientBoostingClassifier

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.features import get_covid_feature_matrix, COVID_FEATURES, COVID_OUTCOMES
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

logger = get_logger("train_covid")

MIN_POSITIVES = 30


def train_covid_outcome_models() -> Dict[str, Any]:
    """
    Train one classifier per COVID-19 outcome and register them as a single artifact.
    """
    models, all_metrics = {}, {}
    for outcome, label in COVID_OUTCOMES.items():
        X, y, feature_cols = get_covid_feature_matrix(outcome)
        if X.empty or int(y.sum()) < MIN_POSITIVES:
            logger.warning(f"Skipping {outcome}: too few positive events ({int(y.sum()) if len(y) else 0}).")
            continue

        # One row per patient, so a stratified split is already patient-disjoint
        train_idx, test_idx = holdout_split(X, y, groups=None)
        X_train, X_test, y_train, y_test = X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]

        clf = HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.05,
            max_depth=4,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
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
        logger.info(
            f"COVID {outcome}: ROC-AUC {metrics['roc_auc']} (CV {metrics['cv_roc_auc_mean']}±{metrics['cv_roc_auc_std']}) "
            f"vs age-only {metrics['baseline_roc_auc_age_only']} | PR-AUC {metrics['pr_auc']} @ prevalence {metrics['positive_rate']}"
        )

    if not models:
        return {"status": "FAILED", "error": "No COVID-19 outcome had enough events to train"}

    model_artifact = {
        "models": models,
        "features": COVID_FEATURES,
        "metrics": all_metrics,
        "version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "type": "covid_outcome_classifiers",
    }
    path = register_model(
        model_name="covid_outcome_model",
        version="1.0.0",
        dataset="gold_covid_outcomes",
        features=COVID_FEATURES,
        metrics=all_metrics,
        model_obj=model_artifact,
        filename="covid_outcome_model.joblib",
    )
    return {"status": "SUCCESS", "model_name": "covid_outcome_model", "path": path, "metrics": all_metrics}


if __name__ == "__main__":
    train_covid_outcome_models()
