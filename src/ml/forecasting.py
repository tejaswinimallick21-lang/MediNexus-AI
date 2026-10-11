"""
Operational demand forecasting (lab workload, inpatient admissions, pharmacy demand).

Every forecast predicts a FUTURE window from information available at the forecast date `t`
(trailing windows ending at t), is evaluated on a later, held-out time period, and is compared
with naive persistence baselines. Training and inference share the feature builders below.

Daily-series models predict the log-ratio of the next-7-day average to the trailing 7-day
average, so they stay scale-free through the 2020 COVID-19 volume surge in the Synthea data.

Three daily methods compete in the backtest and the most accurate one is served:
- the gradient-boosting model;
- naive-7 (repeat the last 7-day average);
- surge-aware average: the steadier 7/28-day blend in normal times, naive-7 once volume has
  shifted sharply (the blend lags a surge; naive-7 is noisy when volume is stable).
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.database import query_df_strict

HISTORY_DAYS = 3 * 365      # training history kept for daily series
HORIZON_DAYS = 7            # daily-series forecast window (t+1 .. t+7)
TEST_DAYS = 60              # final period held out for evaluation
PHARMACY_HORIZON = 30
DAILY_FEATURES = ["log_mean7", "log_mean28", "log_mean91", "trend_7_28", "trend_28_91", "last_vs_mean7", "zero_share_28", "month",
                  "doy_sin", "doy_cos", "yoy_change"]
PHARMACY_FEATURES = ["u30", "u90", "u180", "active_rx", "new_rx_30", "trend_30_90", "unit_cost"]
SURGE_THRESHOLD = 0.3       # |log 7-day avg - log 28-day avg| above this (about a 35% shift) = surge


# ---------------------------------------------------------------------------------------------
# Daily series (lab categories, network admissions)
# ---------------------------------------------------------------------------------------------

def _complete_daily(df: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Fill missing days with zero counts per group over [end - HISTORY_DAYS, end]."""
    start = end - pd.Timedelta(days=HISTORY_DAYS)
    days = pd.date_range(start, end, freq="D")
    frames = []
    for group, g in df.groupby("group"):
        s = g.set_index("day")["n"].reindex(days, fill_value=0)
        frames.append(pd.DataFrame({"day": days, "group": group, "n": s.values}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["day", "group", "n"])


def lab_daily_series() -> Tuple[pd.DataFrame, pd.Timestamp]:
    end = pd.Timestamp(query_df_strict("SELECT max(test_date) AS d FROM gold_laboratory").iloc[0]["d"])
    df = query_df_strict(
        "SELECT CAST(test_date AS DATE) AS day, test_category AS grp, COUNT(*) AS n FROM gold_laboratory "
        "WHERE test_date >= ? AND test_category IS NOT NULL GROUP BY 1, 2",
        [str((end - pd.Timedelta(days=HISTORY_DAYS)).date())],
    ).rename(columns={"grp": "group"})
    df["day"] = pd.to_datetime(df["day"])
    return _complete_daily(df, end), end


def admissions_daily_series() -> Tuple[pd.DataFrame, pd.Timestamp]:
    end = pd.Timestamp(query_df_strict("SELECT max(admission_date) AS d FROM gold_admissions").iloc[0]["d"])
    df = query_df_strict(
        "SELECT CAST(admission_date AS DATE) AS day, 'All hospitals' AS grp, COUNT(*) AS n FROM gold_admissions "
        "WHERE admission_date >= ? GROUP BY 1, 2",
        [str((end - pd.Timedelta(days=HISTORY_DAYS)).date())],
    ).rename(columns={"grp": "group"})
    df["day"] = pd.to_datetime(df["day"])
    return _complete_daily(df, end), end


def daily_supervised(series: pd.DataFrame) -> pd.DataFrame:
    """One row per (group, day t): trailing-window features at t and the next-7-day average target."""
    out = []
    for group, g in series.sort_values("day").groupby("group"):
        n = g["n"].astype(float).reset_index(drop=True)
        f = pd.DataFrame({"day": g["day"].values, "group": group, "n": n})
        f["mean7"] = n.rolling(7, min_periods=7).mean()
        f["mean28"] = n.rolling(28, min_periods=28).mean()
        f["mean91"] = n.rolling(91, min_periods=91).mean()
        f["zero_share_28"] = (n == 0).astype(float).rolling(28, min_periods=28).mean()
        # target: mean of t+1..t+7 (shift so it is aligned with day t)
        f["target"] = n[::-1].rolling(HORIZON_DAYS, min_periods=HORIZON_DAYS).mean()[::-1].shift(-1)
        # Seasonality from the past: how the same 7-day window moved one year earlier (known at time t)
        f["yoy_change"] = np.log1p(f["target"].shift(364)) - np.log1p(f["mean7"].shift(364))
        out.append(f)
    df = pd.concat(out, ignore_index=True).dropna(subset=["mean91"])
    df["log_mean7"] = np.log1p(df["mean7"])
    df["log_mean28"] = np.log1p(df["mean28"])
    df["log_mean91"] = np.log1p(df["mean91"])
    df["trend_7_28"] = df["log_mean7"] - df["log_mean28"]
    df["trend_28_91"] = df["log_mean28"] - df["log_mean91"]
    df["last_vs_mean7"] = np.log1p(df["n"]) - df["log_mean7"]
    df["month"] = pd.to_datetime(df["day"]).dt.month
    doy = pd.to_datetime(df["day"]).dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["log_ratio_target"] = np.log1p(df["target"]) - df["log_mean7"]
    return df


def outpatient_daily_series() -> Tuple[pd.DataFrame, pd.Timestamp]:
    """SIMULATED: outpatient visit demand per hospital (sim_outpatient_daily)."""
    df = query_df_strict("SELECT CAST(date AS DATE) AS day, hospital_id AS grp, demand AS n FROM sim_outpatient_daily").rename(columns={"grp": "group"})
    df["day"] = pd.to_datetime(df["day"])
    return df, df["day"].max()


def pharmacy_class_series() -> Tuple[pd.DataFrame, pd.Timestamp]:
    """SIMULATED: network-wide units dispensed per drug class (sim_pharmacy_daily)."""
    df = query_df_strict("SELECT CAST(date AS DATE) AS day, drug_class AS grp, SUM(units_dispensed) AS n FROM sim_pharmacy_daily GROUP BY 1, 2").rename(columns={"grp": "group"})
    df["day"] = pd.to_datetime(df["day"])
    return df, df["day"].max()


def rolling_backtest(sup: pd.DataFrame, end: pd.Timestamp, make_model, folds: int = 6, step_days: int = 60) -> List[Dict]:
    """
    Rolling-origin evaluation: for each fold, train on forecasts whose target window closed before the
    fold starts, then score forecasts made inside the fold. Folds tile the most recent folds × step_days.
    """
    labelled = sup.dropna(subset=["target"])
    results = []
    for k in range(folds, 0, -1):
        start = end - pd.Timedelta(days=k * step_days + HORIZON_DAYS)
        stop = start + pd.Timedelta(days=step_days)
        train = labelled[labelled["day"] < start - pd.Timedelta(days=HORIZON_DAYS)]
        test = labelled[(labelled["day"] >= start) & (labelled["day"] < stop)]
        if len(train) < 200 or test.empty:
            continue
        model = make_model().fit(train[DAILY_FEATURES], train["log_ratio_target"])
        y = test["target"].to_numpy()
        m = regression_scores(y, predict_daily(model, test))
        b = regression_scores(y, test["mean7"].to_numpy())
        s = regression_scores(y, surge_aware(test["mean7"], test["mean28"]))
        results.append({
            "fold_start": str(start.date()), "fold_end": str((stop - pd.Timedelta(days=1)).date()),
            "mae": m["mae"], "baseline_mae": b["mae"], "wape_pct": m["wape_pct"], "baseline_wape_pct": b["wape_pct"],
            "surge_mae": s["mae"], "surge_wape_pct": s["wape_pct"],
            "covid_period": bool(stop > pd.Timestamp("2020-03-10")),
        })
    return results


def surge_aware(mean7, mean28) -> np.ndarray:
    """7/28-day blend while volume is stable; the 7-day average once it has shifted sharply."""
    m7, m28 = np.asarray(mean7, dtype=float), np.asarray(mean28, dtype=float)
    shifted = np.abs(np.log1p(m7) - np.log1p(m28)) > SURGE_THRESHOLD
    return np.where(shifted, m7, 0.5 * m7 + 0.5 * m28)


def predict_daily(model, frame: pd.DataFrame) -> np.ndarray:
    """Model predicts the log-ratio vs the trailing 7-day mean; convert back to a daily volume."""
    ratio = model.predict(frame[DAILY_FEATURES])
    return np.clip(np.expm1(frame["log_mean7"].to_numpy() + ratio), 0, None)


def time_split(df: pd.DataFrame, end: pd.Timestamp) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Test = forecast dates in the last TEST_DAYS with a complete target window.
    Train = forecast dates whose target window ends before the test period starts (no overlap)."""
    labelled = df.dropna(subset=["target"])
    test_start = end - pd.Timedelta(days=TEST_DAYS + HORIZON_DAYS)
    train = labelled[labelled["day"] < test_start - pd.Timedelta(days=HORIZON_DAYS)]
    test = labelled[labelled["day"] >= test_start]
    return train, test


def regression_scores(y: np.ndarray, pred: np.ndarray) -> Dict[str, float]:
    err = np.abs(y - pred)
    return {
        "mae": round(float(err.mean()), 3),
        "wape_pct": round(float(err.sum() / max(1e-9, np.abs(y).sum()) * 100), 2),
    }


# ---------------------------------------------------------------------------------------------
# Pharmacy demand (site × medication, 30-day horizon)
# ---------------------------------------------------------------------------------------------

def pharmacy_frame(cutoffs: List[pd.Timestamp], data_end: pd.Timestamp, pairs: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Units dispensed per (hospital, medication) in trailing windows ending at each cutoff, and the
    target: units dispensed in the following 30 days. A prescription's recorded dispense count is
    spread evenly over its active period (ongoing prescriptions run to the end of the data).
    """
    cut = pd.DataFrame({"t": pd.to_datetime(cutoffs)})
    pair_filter = ""
    params: list = [str(data_end.date()), str((min(cutoffs) - pd.Timedelta(days=180)).date())]
    if pairs is not None:
        pair_filter = "AND (hospital_id, medication_id) IN (SELECT hospital_id, medication_id FROM pairs)"
    sql = f"""
        WITH rx AS (
            SELECT hospital_id AS h, medication_id AS m,
                   CAST(prescription_date AS DATE) AS s,
                   CAST(coalesce(end_date, ?) AS DATE) AS e,
                   TRY_CAST(quantity AS DOUBLE) AS q
            FROM gold_prescriptions
            WHERE hospital_id IS NOT NULL AND medication_id IS NOT NULL {pair_filter}
        ),
        rx2 AS (
            SELECT *, q / greatest(date_diff('day', s, e), 1) AS rate FROM rx
            WHERE q IS NOT NULL AND e >= CAST(? AS DATE)
        )
        SELECT c.t, h AS hospital_id, m AS medication_id,
               sum(rate * greatest(0, date_diff('day', greatest(s, c.t - INTERVAL 30 DAY), least(e, c.t)))) AS u30,
               sum(rate * greatest(0, date_diff('day', greatest(s, c.t - INTERVAL 90 DAY), least(e, c.t)))) AS u90,
               sum(rate * greatest(0, date_diff('day', greatest(s, c.t - INTERVAL 180 DAY), least(e, c.t)))) AS u180,
               sum(rate * greatest(0, date_diff('day', greatest(s, c.t), least(e, c.t + INTERVAL {PHARMACY_HORIZON} DAY)))) AS y30,
               count(*) FILTER (WHERE s <= c.t AND e >= c.t) AS active_rx,
               count(*) FILTER (WHERE s > c.t - INTERVAL 30 DAY AND s <= c.t) AS new_rx_30
        FROM cut c JOIN rx2 ON rx2.s <= c.t + INTERVAL {PHARMACY_HORIZON} DAY AND rx2.e >= c.t - INTERVAL 180 DAY
        GROUP BY 1, 2, 3
    """
    from src.utils.database import _DB_LOCK, connect, DataUnavailableError  # local import keeps module import light

    with _DB_LOCK:
        con = connect(read_only=True)
        try:
            con.register("cut", cut)
            if pairs is not None:
                con.register("pairs", pairs[["hospital_id", "medication_id"]])
            df = con.execute(sql, params).df()
        except Exception as e:
            raise DataUnavailableError(str(e)) from e
        finally:
            con.close()

    costs = query_df_strict("SELECT medication_id, TRY_CAST(unit_cost AS DOUBLE) AS unit_cost FROM silver_medications")
    df = df.merge(costs, on="medication_id", how="left")
    df["unit_cost"] = df["unit_cost"].fillna(0.0)
    df["trend_30_90"] = (df["u30"] + 1) / (df["u90"] / 3 + 1)
    return df
