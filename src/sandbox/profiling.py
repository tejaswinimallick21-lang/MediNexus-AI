"""
Automatic profiling of a cleaned upload: distributions, correlations, outliers, clusters,
anomalies and drift against the live lakehouse table it most resembles.
"""

from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

SAMPLE = 20_000  # rows used for clustering / anomaly detection
MAX_NUMERIC = 12
MAX_CATEGORY = 8


def _numeric_cols(df: pd.DataFrame, kinds: Dict[str, str]) -> List[str]:
    return [c for c, k in kinds.items() if k == "numeric" and c in df and df[c].notna().sum() >= 10 and df[c].nunique() > 1]


def numeric_summary(df: pd.DataFrame, cols: List[str]) -> List[Dict[str, Any]]:
    out = []
    for c in cols[:MAX_NUMERIC]:
        s = df[c].dropna().astype(float)
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        extreme = int(((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum()) if iqr > 0 else 0
        counts, edges = np.histogram(s, bins=12)
        out.append({
            "column": c, "mean": float(s.mean()), "std": float(s.std(ddof=0)), "min": float(s.min()), "p25": float(q1),
            "median": float(s.median()), "p75": float(q3), "max": float(s.max()), "missing_pct": round(float(df[c].isna().mean() * 100), 2),
            "extreme_outliers": extreme,
            "histogram": [{"bin": f"{edges[i]:.4g}–{edges[i + 1]:.4g}", "count": int(counts[i])} for i in range(len(counts))],
        })
    return out


def category_summary(df: pd.DataFrame, kinds: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for c, k in kinds.items():
        if k in ("category", "boolean") and c in df:
            vc = df[c].astype("string").value_counts(dropna=True)
            if vc.empty:
                continue
            total = int(vc.sum())
            out.append({
                "column": c, "distinct": int(len(vc)),
                "top": [{"value": str(v), "count": int(n), "share_pct": round(n / total * 100, 1)} for v, n in vc.head(MAX_CATEGORY).items()],
            })
    return out[:MAX_NUMERIC]


def top_correlations(df: pd.DataFrame, cols: List[str], limit: int = 8) -> List[Dict[str, Any]]:
    if len(cols) < 2:
        return []
    corr = df[cols].astype(float).corr(method="spearman", min_periods=30)
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r):
                pairs.append({"a": a, "b": b, "rho": round(float(r), 3)})
    pairs.sort(key=lambda p: abs(p["rho"]), reverse=True)
    return [p for p in pairs if abs(p["rho"]) >= 0.2][:limit]


def clusters_and_anomalies(df: pd.DataFrame, cols: List[str], seed: int = 7) -> Dict[str, Any]:
    """KMeans with k chosen by silhouette (2–6) on standardised numeric columns; IsolationForest anomaly share."""
    from sklearn.cluster import KMeans
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    # Flags and small counts (≤5 distinct values) distort distance-based clustering; use continuous measures only
    use = [c for c in cols if df[c].nunique() > 5][:MAX_NUMERIC]
    if len(use) < 2:
        return {"available": False, "reason": "Needs at least two continuous numeric columns."}
    X = df[use].astype(float)
    X = X.fillna(X.median())
    if len(X) < 60:
        return {"available": False, "reason": "Needs at least 60 rows."}
    X = X.sample(min(SAMPLE, len(X)), random_state=seed)
    Z = StandardScaler().fit_transform(X)

    best = None
    for k in range(2, 7):
        km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(Z)
        score = silhouette_score(Z, km.labels_, sample_size=min(3000, len(Z)), random_state=seed)
        if best is None or score > best[0]:
            best = (score, k, km)
    score, k, km = best
    labels = km.labels_
    centroids = pd.DataFrame(km.cluster_centers_, columns=use)
    groups = []
    for ci in range(k):
        z = centroids.iloc[ci]
        top = z.abs().sort_values(ascending=False).head(3).index
        groups.append({
            "cluster": ci + 1, "size": int((labels == ci).sum()), "share_pct": round(float((labels == ci).mean() * 100), 1),
            "traits": [f"{'higher' if z[c] > 0 else 'lower'} {c} ({X[c][labels == ci].median():.4g} vs {X[c].median():.4g} overall)" for c in top],
        })
    # Anomalies: isolation-forest scores more than 3 robust standard deviations below the median
    scores = IsolationForest(random_state=seed).fit(Z).score_samples(Z)
    mad = np.median(np.abs(scores - np.median(scores))) * 1.4826
    anomalies = int((scores < np.median(scores) - 3 * mad).sum()) if mad > 0 else 0
    return {
        "available": True, "rows_used": int(len(X)), "k": int(k), "silhouette": round(float(score), 3),
        "structure": "clear" if score >= 0.5 else "moderate" if score >= 0.3 else "weak",
        "clusters": sorted(groups, key=lambda g: -g["size"]),
        "anomaly_share_pct": round(anomalies / len(X) * 100, 2), "anomalies": anomalies,
    }


def _psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    """Population stability index on quantile bins of the reference distribution."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    e = np.histogram(expected, bins=edges)[0] / len(expected)
    a = np.histogram(np.clip(actual, edges[0], edges[-1]), bins=edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def drift_vs_lakehouse(df: pd.DataFrame, kinds: Dict[str, str], reference_loader: Callable[[], Dict[str, List[str]]],
                       sample_loader: Callable[[str, List[str]], pd.DataFrame]) -> Dict[str, Any]:
    """Compare shared numeric columns with the Gold table that has the most column names in common."""
    try:
        tables = reference_loader()
    except Exception:
        return {"available": False, "reason": "The live lakehouse is not available for comparison."}
    numeric = set(_numeric_cols(df, kinds))
    best = max(tables.items(), key=lambda kv: len(numeric & set(kv[1])), default=(None, []))
    shared = sorted(numeric & set(best[1]))
    if not best[0] or len(shared) < 3:
        return {"available": False, "reason": "Fewer than 3 numeric columns in common with any live Gold table, so a comparison would not be meaningful."}
    ref = sample_loader(best[0], shared)
    rows = []
    for c in shared:
        r, u = ref[c].dropna().astype(float), df[c].dropna().astype(float)
        if len(r) < 30 or len(u) < 30:
            continue
        psi = _psi(r.to_numpy(), u.to_numpy())
        rows.append({"column": c, "upload_median": float(u.median()), "lakehouse_median": float(r.median()), "psi": round(psi, 3),
                     "shift": "major" if psi >= 0.25 else "moderate" if psi >= 0.1 else "stable"})
    if not rows:
        return {"available": False, "reason": "Too few values to compare."}
    return {"available": True, "reference_table": best[0], "columns": rows}


def profile(df: pd.DataFrame, kinds: Dict[str, str], reference_loader: Optional[Callable] = None, sample_loader: Optional[Callable] = None) -> Dict[str, Any]:
    num = _numeric_cols(df, kinds)
    date_cols = [c for c, k in kinds.items() if k == "datetime" and c in df and df[c].notna().any()]
    coverage = None
    if date_cols:
        c = max(date_cols, key=lambda d: df[d].notna().sum())
        coverage = {"column": c, "start": str(df[c].min().date()), "end": str(df[c].max().date())}
    result = {
        "rows": int(len(df)), "columns": int(df.shape[1]),
        "numeric": numeric_summary(df, num), "categories": category_summary(df, kinds),
        "correlations": top_correlations(df, num[:MAX_NUMERIC]), "date_coverage": coverage,
        "segments": clusters_and_anomalies(df, num),
    }
    result["drift"] = (drift_vs_lakehouse(df, kinds, reference_loader, sample_loader) if reference_loader and sample_loader
                       else {"available": False, "reason": "Comparison disabled."})
    return result
