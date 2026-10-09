"""
Shared, leakage-aware evaluation helpers for MediNexus AI classifiers.

Every reported score is out-of-sample, split by patient when a patient can contribute
several rows, and shown next to a simple baseline so the lift is visible.
"""

from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, StratifiedKFold, StratifiedShuffleSplit
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)


def holdout_split(X: pd.DataFrame, y: pd.Series, groups: Optional[pd.Series], test_size: float = 0.2, seed: int = 42):
    """80/20 split; grouped by patient when groups are given, stratified otherwise."""
    if groups is not None:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(X, y, groups))
    else:
        splitter = StratifiedShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(X, y))
    return train_idx, test_idx


def cross_validated_auc(model, X: pd.DataFrame, y: pd.Series, groups: Optional[pd.Series], folds: int = 5, seed: int = 42) -> Dict[str, float]:
    """Mean and spread of ROC-AUC across folds (shows how stable a small-sample result is)."""
    if groups is not None:
        cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
        splits = cv.split(X, y, groups)
    else:
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        splits = cv.split(X, y)
    aucs = []
    for train_idx, test_idx in splits:
        if y.iloc[test_idx].nunique() < 2:
            continue
        fold_model = clone(model).fit(X.iloc[train_idx], y.iloc[train_idx])
        aucs.append(roc_auc_score(y.iloc[test_idx], fold_model.predict_proba(X.iloc[test_idx])[:, 1]))
    if not aucs:
        return {"cv_roc_auc_mean": float("nan"), "cv_roc_auc_std": float("nan"), "cv_folds": 0}
    return {"cv_roc_auc_mean": round(float(np.mean(aucs)), 4), "cv_roc_auc_std": round(float(np.std(aucs)), 4), "cv_folds": len(aucs)}


def baseline_auc(X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame, y_test: pd.Series, baseline_features: List[str]) -> float:
    """ROC-AUC of a logistic regression on a few obvious features (e.g. age only)."""
    cols = [c for c in baseline_features if c in X_train.columns]
    if not cols:
        return float("nan")
    fill = X_train[cols].median()
    lr = LogisticRegression(max_iter=1000).fit(X_train[cols].fillna(fill), y_train)
    return round(float(roc_auc_score(y_test, lr.predict_proba(X_test[cols].fillna(fill))[:, 1])), 4)


def classification_report(y_test: pd.Series, proba: np.ndarray, threshold: float) -> Dict[str, Any]:
    """Out-of-sample metrics at a decision threshold, plus threshold-free ranking metrics."""
    pred = (proba >= threshold).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
        "brier_score": round(float(brier_score_loss(y_test, proba)), 4),
        "decision_threshold": round(float(threshold), 4),
        "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_test, pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_test, pred, labels=[0, 1]).tolist(),
        "test_samples": int(len(y_test)),
        "test_positives": int(y_test.sum()),
    }


def risk_band_thresholds(proba: np.ndarray) -> Dict[str, float]:
    """Cohort-relative risk bands: top 10% = HIGH, next 15% = MODERATE (from held-out predictions)."""
    return {
        "high": round(float(np.quantile(proba, 0.90)), 4),
        "moderate": round(float(np.quantile(proba, 0.75)), 4),
    }


def top_feature_importances(model, feature_cols: List[str], X: pd.DataFrame, y: pd.Series, k: int = 8) -> List[Dict[str, Any]]:
    """Permutation importance on held-out data (works for any estimator, unlike impurity importance)."""
    from sklearn.inspection import permutation_importance

    scoring = "roc_auc" if y.nunique() == 2 else "neg_mean_absolute_error"
    result = permutation_importance(model, X, y, scoring=scoring, n_repeats=5, random_state=42, n_jobs=-1)
    ranked = sorted(zip(feature_cols, result.importances_mean), key=lambda t: t[1], reverse=True)
    return [{"feature": f, "importance": round(float(v), 4)} for f, v in ranked[:k]]
