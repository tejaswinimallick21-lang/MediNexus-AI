"""
"Predict a column" on an uploaded table, with the same honesty rules as the platform models:

- the split respects time (if there is a date column) or groups (if there is an identifier that
  repeats), otherwise a stratified random split;
- identifiers, pseudonymised columns and suspected leakage are excluded before training;
- the model is always compared with a simple baseline on the same held-out rows.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MIN_ROWS = 50
MAX_CLASSES = 20
MAX_TRAIN_ROWS = 200_000
LEAK_AUC = 0.97  # a single column that alone separates the classes this well is suspect
LEAK_R2 = 0.97


def _task(y: pd.Series, kind: str) -> str:
    if kind in ("boolean", "category") or y.dtype == object or str(y.dtype) == "string":
        return "classification"
    return "classification" if y.dropna().nunique() <= 10 and np.allclose(y.dropna() % 1, 0) else "regression"


def _features(df: pd.DataFrame, kinds: Dict[str, str], target: str, pii: List[str]) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    excluded: List[Dict[str, str]] = []
    X = pd.DataFrame(index=df.index)
    for c, k in kinds.items():
        if c == target or c not in df:
            continue
        if c in pii:
            excluded.append({"column": c, "reason": "personal identifier (pseudonymised)"})
        elif k == "identifier":
            excluded.append({"column": c, "reason": "identifier: unique per row, carries no general signal"})
        elif k == "text":
            excluded.append({"column": c, "reason": "free text (not used by this model)"})
        elif k == "datetime":
            d = df[c]
            X[f"{c}__month"] = d.dt.month
            X[f"{c}__dow"] = d.dt.dayofweek
        elif len(c) >= 4 and len(target) >= 4 and (target in c or c in target):
            excluded.append({"column": c, "reason": f"name overlaps the target '{target}' — likely a derived or duplicate outcome"})
        elif k == "boolean":
            X[c] = df[c].astype("float")
        elif k == "category":
            X[c] = df[c].astype(object).where(df[c].notna(), np.nan)  # sklearn encoders need np.nan, not pd.NA
        else:
            X[c] = df[c].astype(float)
    return X, excluded


def _split(df: pd.DataFrame, kinds: Dict[str, str], y: pd.Series, task: str, seed: int, pii: List[str]):
    """Returns (train_idx, test_idx, description)."""
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    dates = [c for c, k in kinds.items() if k == "datetime" and c in df and df[c].notna().mean() > 0.9]
    if dates:
        c = max(dates, key=lambda d: df[d].notna().sum())
        order = df[c].sort_values(kind="stable").index
        cut = int(len(order) * 0.8)
        return order[:cut], order[cut:], f"time-based: train on the earliest 80% by {c}, test on the latest 20%"
    groups = [c for c, k in kinds.items() if k == "identifier" and c in df and c not in pii and df[c].notna().mean() > 0.95
              and 1.2 < len(df) / max(1, df[c].nunique()) < len(df) / 2]
    if groups:
        g = groups[0]
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(df, y, df[g].astype(str)))
        return df.index[tr], df.index[te], f"grouped by {g}: no {g} appears in both train and test"
    strat = y if task == "classification" and y.value_counts().min() >= 2 else None
    tr, te = train_test_split(df.index, test_size=0.2, random_state=seed, stratify=strat)
    return tr, te, "random 80/20 split" + (" stratified by the target" if strat is not None else "")


def _pipeline(X: pd.DataFrame, task: str, seed: int):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

    cat = [c for c in X.columns if X[c].dtype == object]
    pre = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-2), cat)],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    model = (HistGradientBoostingClassifier(random_state=seed, max_iter=200, learning_rate=0.08) if task == "classification"
             else HistGradientBoostingRegressor(random_state=seed, max_iter=200, learning_rate=0.08))
    return Pipeline([("pre", pre), ("model", model)]), cat


def _leak_screen(X: pd.DataFrame, y: pd.Series, task: str, seed: int) -> List[str]:
    """Columns that alone predict the target almost perfectly (cross-validated depth-3 tree)."""
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OrdinalEncoder
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    sample = X.sample(min(len(X), 5000), random_state=seed)
    ys = y.loc[sample.index]
    suspects = []
    binary = task == "classification" and ys.nunique() == 2
    for c in sample.columns:
        col = sample[[c]]
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-2)
        col = enc.fit_transform(col.astype(object).fillna("__missing__")) if col[c].dtype == object else col.fillna(-999)
        try:
            if task == "classification":
                if not binary:
                    continue
                score = cross_val_score(DecisionTreeClassifier(max_depth=3, random_state=seed), col, ys, cv=3, scoring="roc_auc").mean()
                if score >= LEAK_AUC:
                    suspects.append(c)
            else:
                score = cross_val_score(DecisionTreeRegressor(max_depth=3, random_state=seed), col, ys, cv=3, scoring="r2").mean()
                if score >= LEAK_R2:
                    suspects.append(c)
        except ValueError:
            continue
    return suspects


def predict_column(df: pd.DataFrame, kinds: Dict[str, str], target: str, pii: List[str], seed: int = 7) -> Dict[str, Any]:
    from sklearn import metrics
    from sklearn.inspection import permutation_importance

    if target not in df:
        raise ValueError(f"Column '{target}' is not in the cleaned table.")
    if kinds.get(target) in ("identifier", "text", "datetime") or target in pii:
        raise ValueError(f"'{target}' is an identifier, free text or a date; choose a numeric or categorical column to predict.")
    data = df[df[target].notna()]
    if len(data) > MAX_TRAIN_ROWS:
        data = data.sample(MAX_TRAIN_ROWS, random_state=seed)
    if len(data) < MIN_ROWS:
        raise ValueError(f"Need at least {MIN_ROWS} rows with a value in '{target}'.")

    y = data[target]
    task = _task(y, kinds.get(target, ""))
    if task == "classification":
        y = y.astype("string")
        if y.nunique() < 2:
            raise ValueError(f"'{target}' has only one value; there is nothing to predict.")
        if y.nunique() > MAX_CLASSES:
            raise ValueError(f"'{target}' has {y.nunique()} classes; the sandbox predicts up to {MAX_CLASSES}.")
    else:
        y = y.astype(float)

    X, excluded = _features(data, kinds, target, pii)
    leaks = _leak_screen(X, y, task, seed)
    for c in leaks:
        excluded.append({"column": c, "reason": "suspected leakage: on its own it predicts the target almost perfectly"})
    X = X.drop(columns=leaks)
    if X.shape[1] == 0:
        raise ValueError("No usable feature columns remain after excluding identifiers and suspected leakage.")

    tr, te, split = _split(data, kinds, y, task, seed, pii)
    pipe, _ = _pipeline(X, task, seed)
    pipe.fit(X.loc[tr], y.loc[tr])
    Xte, yte = X.loc[te], y.loc[te]

    result: Dict[str, Any] = {"target": target, "task": task, "rows_used": int(len(data)), "train_rows": int(len(tr)), "test_rows": int(len(te)),
                              "split": split, "features_used": list(X.columns), "excluded": excluded}
    if task == "classification":
        majority = y.loc[tr].value_counts().index[0]
        pred = pipe.predict(Xte)
        result.update({
            "classes": int(y.nunique()),
            "accuracy": round(float(metrics.accuracy_score(yte, pred)), 4),
            "baseline_accuracy": round(float((yte == majority).mean()), 4),
            "macro_f1": round(float(metrics.f1_score(yte, pred, average="macro")), 4),
            "baseline_label": f"always predict '{majority}'",
        })
        if y.nunique() == 2 and yte.nunique() == 2:
            pos = pipe.classes_[1]
            proba = pipe.predict_proba(Xte)[:, 1]
            result["roc_auc"] = round(float(metrics.roc_auc_score(yte == pos, proba)), 4)
            result["positive_class"] = str(pos)
            result["primary_metric"], result["score"], result["baseline_score"] = "ROC-AUC", result["roc_auc"], 0.5
        else:
            result["primary_metric"], result["score"], result["baseline_score"] = "Macro F1", result["macro_f1"], round(float(
                metrics.f1_score(yte, np.full(len(yte), majority), average="macro")), 4)
        higher_better = True
        scoring = "roc_auc" if result["primary_metric"] == "ROC-AUC" else "f1_macro"
    else:
        median = float(y.loc[tr].median())
        pred = pipe.predict(Xte)
        result.update({
            "mae": round(float(metrics.mean_absolute_error(yte, pred)), 4),
            "baseline_mae": round(float(metrics.mean_absolute_error(yte, np.full(len(yte), median))), 4),
            "r2": round(float(metrics.r2_score(yte, pred)), 4),
            "baseline_label": f"always predict the training median ({median:.4g})",
        })
        result["primary_metric"], result["score"], result["baseline_score"] = "MAE", result["mae"], result["baseline_mae"]
        higher_better = False
        scoring = "neg_mean_absolute_error"

    lift = (result["score"] - result["baseline_score"]) if higher_better else (result["baseline_score"] - result["score"])
    result["beats_baseline"] = bool(lift > 0.02 * max(abs(result["baseline_score"]), 1e-9))
    result["verdict"] = "Model beats the baseline" if result["beats_baseline"] else "Baseline is as good — the columns carry little signal for this target"

    sample = Xte.sample(min(len(Xte), 2000), random_state=seed)
    imp = permutation_importance(pipe, sample, yte.loc[sample.index], n_repeats=5, random_state=seed, scoring=scoring)
    order = np.argsort(-imp.importances_mean)[:8]
    result["drivers"] = [{"feature": str(sample.columns[i]), "importance": round(float(imp.importances_mean[i]), 4)} for i in order if imp.importances_mean[i] > 0]
    return result
