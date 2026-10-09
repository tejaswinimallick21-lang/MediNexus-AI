"""
Forecast an uploaded table over time: aggregate to a daily or weekly series, score a lag-feature
gradient-boosting model against a seasonal-naive baseline with a rolling-origin backtest, and
serve whichever was more accurate.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

MIN_POINTS = 60


def build_series(df: pd.DataFrame, date_col: str, value_col: Optional[str], agg: str) -> pd.Series:
    d = df[[date_col] + ([value_col] if value_col else [])].dropna(subset=[date_col]).copy()
    d["_day"] = d[date_col].dt.floor("D")
    if value_col:
        s = d.groupby("_day")[value_col].agg("sum" if agg == "sum" else "mean")
    else:
        s = d.groupby("_day").size().astype(float)
    full = pd.date_range(s.index.min(), s.index.max(), freq="D")
    s = s.reindex(full).fillna(0.0 if (value_col is None or agg == "sum") else np.nan).interpolate(limit_direction="both")
    return s


def _choose_freq(s: pd.Series) -> str:
    return "D" if len(s) >= 120 else "W"


def _features(s: pd.Series, season: int) -> pd.DataFrame:
    f = pd.DataFrame(index=s.index)
    for lag in (1, 2, season, 2 * season):
        f[f"lag_{lag}"] = s.shift(lag)
    f["roll_mean"] = s.shift(1).rolling(season).mean()
    if season == 7:
        f["dow"] = s.index.dayofweek
    f["month"] = s.index.month
    return f


def _recursive(model, history: pd.Series, horizon: int, season: int, freq: str) -> List[float]:
    hist = history.copy()
    step = pd.Timedelta(days=1 if freq == "D" else 7)
    out = []
    for _ in range(horizon):
        nxt = hist.index[-1] + step
        hist.loc[nxt] = np.nan
        row = _features(hist, season).iloc[[-1]]
        val = float(max(0.0, model.predict(row)[0])) if hist.min(skipna=True) >= 0 else float(model.predict(row)[0])
        hist.loc[nxt] = val
        out.append(val)
    return out


def forecast(df: pd.DataFrame, date_col: str, value_col: Optional[str] = None, agg: str = "sum", horizon: Optional[int] = None,
             folds: int = 4, seed: int = 7) -> Dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingRegressor

    if date_col not in df or not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        raise ValueError(f"'{date_col}' is not a date column.")
    if value_col and (value_col not in df or not pd.api.types.is_numeric_dtype(df[value_col])):
        raise ValueError(f"'{value_col}' is not a numeric column.")
    daily = build_series(df, date_col, value_col, agg)
    freq = _choose_freq(daily)
    s = daily if freq == "D" else daily.resample("W").sum() if (value_col is None or agg == "sum") else daily.resample("W").mean()
    season = 7 if freq == "D" else 4
    horizon = horizon or (28 if freq == "D" else 8)
    if len(s) < max(MIN_POINTS if freq == "D" else 30, 3 * season + horizon * 2):
        raise ValueError(f"Need a longer history: {len(s)} {'days' if freq == 'D' else 'weeks'} is too short to backtest a {horizon}-step forecast.")

    def make():
        return HistGradientBoostingRegressor(random_state=seed, max_iter=200, learning_rate=0.06)

    model_err, base_err = [], []
    for k in range(folds, 0, -1):
        cut = len(s) - k * horizon
        if cut < 3 * season + 10:
            continue
        train, test = s.iloc[:cut], s.iloc[cut:cut + horizon]
        X = _features(train, season).dropna()
        m = make().fit(X, train.loc[X.index])
        pred = _recursive(m, train, len(test), season, freq)
        naive = [train.iloc[-season + (i % season)] for i in range(len(test))]
        model_err.append(float(np.mean(np.abs(np.array(pred) - test.to_numpy()))))
        base_err.append(float(np.mean(np.abs(np.array(naive) - test.to_numpy()))))
    if not model_err:
        raise ValueError("Not enough history for a backtest.")

    mae, base = float(np.mean(model_err)), float(np.mean(base_err))
    use_model = mae < base * 0.98
    X = _features(s, season).dropna()
    final = make().fit(X, s.loc[X.index])
    future = _recursive(final, s, horizon, season, freq) if use_model else [s.iloc[-season + (i % season)] for i in range(horizon)]
    step = pd.Timedelta(days=1 if freq == "D" else 7)
    dates = [s.index[-1] + step * (i + 1) for i in range(horizon)]
    tail = s.iloc[-min(len(s), 6 * horizon):]
    return {
        "date_column": date_col, "value_column": value_col, "aggregation": "row count" if value_col is None else agg,
        "frequency": "daily" if freq == "D" else "weekly", "horizon": horizon, "history_points": int(len(s)),
        "backtest_folds": len(model_err), "model_mae": round(mae, 4), "baseline_mae": round(base, 4),
        "baseline_label": "same day last week" if freq == "D" else "same week four weeks earlier",
        "serving_method": "model" if use_model else "baseline",
        "skill_pct": round((1 - mae / base) * 100, 1) if base > 0 else 0.0,
        "history": [{"date": str(d.date()), "value": round(float(v), 4)} for d, v in tail.items()],
        "forecast": [{"date": str(d.date()), "value": round(float(v), 4)} for d, v in zip(dates, future)],
        "next_total": round(float(np.sum(future)), 4), "last_total": round(float(s.iloc[-horizon:].sum()), 4),
    }
