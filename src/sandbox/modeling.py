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


def _stem(name: str) -> str:
    """readmitted_30d / readmitted_7d -> readmitted; mortality_flag -> mortality."""
    return re.sub(r"_(?:\d+[a-z]*|flag|yn|binary|ind)$", "", name.split("__")[-1])


TARGET_HINT = re.compile(r"readmi|outcome|target|label|status|churn|death|died|mortal|(^|_)los($|_)|length_of_stay|cost|charge|amount|"
                         r"revenue|risk|flag|result|default|fraud|no_?show|class|disposition", re.I)


POST_EVENT = re.compile(r"discharg|bill|invoice|payment|paid|refund|claim|outcome|death|died|expired|mortal|readmi|follow_?up|after|post_|settle", re.I)


def timing_warnings(drivers: List[str], target: str) -> List[Dict[str, str]]:
    """Strong drivers whose names suggest they are only known after the event being predicted."""
    out = []
    for f in drivers:
        base = f.rsplit("__", 1)[0]
        if POST_EVENT.search(f) and _stem(base) != _stem(target):
            out.append({"feature": f, "note": f"'{f}' may only be known after the moment you would predict {target} (e.g. at discharge or billing). "
                                               "If so, the score is optimistic: remove it and re-run."})
    return out


def suggest_targets(columns: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    """Columns that look like outcomes worth predicting (name hints first, then binary flags)."""
    scored = []
    for c in columns:
        if c["kind"] not in ("numeric", "category", "boolean") or c.get("pii_masked") or c["missing_pct"] > 50 or c["unique"] < 2:
            continue
        if c["name"].endswith(("_count", "_sum", "_mean", "_max", "_distinct", "_n_rows", "_share")):
            continue  # aggregated features from linked tables are inputs, not outcomes
        score = (3 if TARGET_HINT.search(c["name"]) else 0) + (2 if c["kind"] == "boolean" or c["unique"] == 2 else 0) \
            + (1 if c["kind"] == "category" and c["unique"] <= 10 else 0)
        if score:
            scored.append((score, c["name"]))
    return [n for _, n in sorted(scored, key=lambda s: -s[0])[:limit]]


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
        elif _stem(c) == _stem(target) and len(_stem(target)) >= 4:
            excluded.append({"column": c, "reason": f"sibling outcome: the same measure as '{target}' over a different window — it would give the answer away"})
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


def _candidates(X: pd.DataFrame, task: str, seed: int) -> Dict[str, Any]:
    """Two model families: an interpretable linear model and gradient boosting."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    cat = [c for c in X.columns if X[c].dtype == object]
    num = [c for c in X.columns if c not in cat]
    boost_pre = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-2), cat)],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    linear_pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
        ("cat", make_pipeline(SimpleImputer(strategy="constant", fill_value="__missing__"),
                              OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=0.01, max_categories=20, sparse_output=False)), cat),
    ], verbose_feature_names_out=False)
    if task == "classification":
        return {
            "Logistic regression": Pipeline([("pre", linear_pre), ("model", LogisticRegression(max_iter=2000))]),
            "Gradient boosting": Pipeline([("pre", boost_pre), ("model", HistGradientBoostingClassifier(random_state=seed, max_iter=200, learning_rate=0.08))]),
        }
    return {
        "Ridge regression": Pipeline([("pre", linear_pre), ("model", Ridge(alpha=1.0))]),
        "Gradient boosting": Pipeline([("pre", boost_pre), ("model", HistGradientBoostingRegressor(random_state=seed, max_iter=200, learning_rate=0.08))]),
    }


def _score(pipe, X: pd.DataFrame, y: pd.Series, metric: str) -> float:
    from sklearn import metrics

    if metric == "ROC-AUC":
        return float(metrics.roc_auc_score(y == pipe.classes_[1], pipe.predict_proba(X)[:, 1]))
    if metric == "Macro F1":
        return float(metrics.f1_score(y, pipe.predict(X), average="macro"))
    return float(metrics.mean_absolute_error(y, pipe.predict(X)))


def _effects(pipe, X: pd.DataFrame, drivers: List[str], task: str, target: str, binary: bool) -> List[Dict[str, str]]:
    """How each driver moves the model's prediction (an association learned by the model, not a cause)."""
    if task == "classification" and not binary:
        return []
    pred = pipe.predict_proba(X)[:, 1] if task == "classification" else pipe.predict(X)
    pred = pd.Series(pred, index=X.index)
    unit = (lambda v: f"{v * 100:.1f}%") if task == "classification" else (lambda v: f"{v:,.4g}")
    what = f"predicted probability of {target} = {pipe.classes_[1]}" if task == "classification" else f"predicted {target}"
    out = []
    for f in drivers:
        x = X[f]
        if x.dtype == object:
            means = pred.groupby(x).agg(["mean", "size"])
            means = means[means["size"] >= 20].sort_values("mean")
            if len(means) < 2:
                continue
            lo, hi = means.index[0], means.index[-1]
            out.append({"feature": f, "direction": "categorical",
                        "detail": f"The {what} is highest when {f} = {hi} ({unit(means['mean'].iloc[-1])}) and lowest when {f} = {lo} ({unit(means['mean'].iloc[0])})."})
            continue
        x = x.astype(float)
        ok = x.notna()
        if ok.sum() < 30 or x[ok].nunique() < 2:
            continue
        q1, q3 = x[ok].quantile([0.25, 0.75])
        low, high = pred[ok & (x <= q1)].mean(), pred[ok & (x >= q3)].mean()
        rho = x[ok].corr(pred[ok], method="spearman")
        direction = "up" if rho > 0.1 else "down" if rho < -0.1 else "mixed"
        if direction == "mixed":
            text = f"{f} has no simple one-way effect on the {what} ({unit(low)} in its lowest quarter vs {unit(high)} in its highest)."
        else:
            text = f"Higher {f} {'raises' if direction == 'up' else 'lowers'} the {what}: {unit(low)} in its lowest quarter vs {unit(high)} in its highest."
        out.append({"feature": f, "direction": direction, "detail": text})
    return out


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
    from sklearn.base import clone
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
    binary = task == "classification" and y.nunique() == 2
    metric = "ROC-AUC" if binary else "Macro F1" if task == "classification" else "MAE"
    higher_better = metric != "MAE"

    X, excluded = _features(data, kinds, target, pii)
    leaks = _leak_screen(X, y, task, seed)
    for c in leaks:
        excluded.append({"column": c, "reason": "suspected leakage: on its own it predicts the target almost perfectly"})
    X = X.drop(columns=leaks)
    if X.shape[1] == 0:
        raise ValueError("No usable feature columns remain after excluding identifiers and suspected leakage.")

    tr, te, split = _split(data, kinds, y, task, seed, pii)
    # Model selection uses a validation slice of the training rows (the latest 20% when the split is by time);
    # the test rows are used once, for the final score.
    cut = int(len(tr) * 0.8)
    if split.startswith("time-based"):
        fit_idx, val_idx = tr[:cut], tr[cut:]
    else:
        shuffled = pd.Index(tr).to_series().sample(frac=1, random_state=seed).index
        fit_idx, val_idx = shuffled[:cut], shuffled[cut:]
    comparison: List[Dict[str, Any]] = []
    for name, cand in _candidates(X, task, seed).items():
        try:
            m = clone(cand).fit(X.loc[fit_idx], y.loc[fit_idx])
            comparison.append({"model": name, "validation_score": round(_score(m, X.loc[val_idx], y.loc[val_idx], metric), 4), "selected": False})
        except (ValueError, IndexError):  # e.g. a class missing from the validation slice
            comparison.append({"model": name, "validation_score": None, "selected": False})
    scored = [c for c in comparison if c["validation_score"] is not None]
    best = (max if higher_better else min)(scored, key=lambda c: c["validation_score"]) if scored else comparison[-1]
    best["selected"] = True
    pipe = clone(_candidates(X, task, seed)[best["model"]]).fit(X.loc[tr], y.loc[tr])
    Xte, yte = X.loc[te], y.loc[te]

    result: Dict[str, Any] = {"target": target, "task": task, "rows_used": int(len(data)), "train_rows": int(len(tr)), "test_rows": int(len(te)),
                              "split": split, "features_used": list(X.columns), "excluded": excluded,
                              "selected_model": best["model"], "model_comparison": comparison}
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
        if binary and yte.nunique() == 2:
            result["roc_auc"] = round(_score(pipe, Xte, yte, "ROC-AUC"), 4)
            result["positive_class"] = str(pipe.classes_[1])
            result["positive_rate_pct"] = round(float((y == pipe.classes_[1]).mean() * 100), 2)
            result["primary_metric"], result["score"], result["baseline_score"] = "ROC-AUC", result["roc_auc"], 0.5
        else:
            result["primary_metric"], result["score"], result["baseline_score"] = "Macro F1", result["macro_f1"], round(float(
                metrics.f1_score(yte, np.full(len(yte), majority), average="macro")), 4)
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
        scoring = "neg_mean_absolute_error"

    lift = (result["score"] - result["baseline_score"]) if higher_better else (result["baseline_score"] - result["score"])
    result["beats_baseline"] = bool(lift > 0.02 * max(abs(result["baseline_score"]), 1e-9))
    result["verdict"] = "Model beats the baseline" if result["beats_baseline"] else "Baseline is as good — the columns carry little signal for this target"

    sample = Xte.sample(min(len(Xte), 2000), random_state=seed)
    imp = permutation_importance(pipe, sample, yte.loc[sample.index], n_repeats=5, random_state=seed, scoring=scoring)
    order = np.argsort(-imp.importances_mean)[:8]
    result["drivers"] = [{"feature": str(sample.columns[i]), "importance": round(float(imp.importances_mean[i]), 4)} for i in order if imp.importances_mean[i] > 0]
    result["timing_warnings"] = timing_warnings([d["feature"] for d in result["drivers"]], target)
    result["effects"] = _effects(pipe, sample, [d["feature"] for d in result["drivers"][:6]], task, target, binary) if result["beats_baseline"] else []
    return result
