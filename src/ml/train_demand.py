"""
Models 3, 4, 5: Operational demand forecasts (honest re-implementation).

- Model 3: Pharmacy demand: units dispensed per (site, medication) over the next 30 days.
- Model 4: Laboratory workload: average daily tests per category over the next 7 days.
- Model 5: Admission demand: average daily network admissions over the next 7 days.

All features end at the forecast date; evaluation uses a later, held-out time period; every
model is compared with naive persistence baselines. After evaluation the model is refit on all
labelled history for inference (metrics always describe the held-out period).
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ml.forecasting import (
    DAILY_FEATURES,
    HORIZON_DAYS,
    PHARMACY_FEATURES,
    PHARMACY_HORIZON,
    admissions_daily_series,
    daily_supervised,
    lab_daily_series,
    outpatient_daily_series,
    pharmacy_class_series,
    pharmacy_frame,
    regression_scores,
    rolling_backtest,
)
from src.ml.model_registry import register_model
from src.utils.database import query_df_strict
from src.utils.logging_utils import get_logger

logger = get_logger("train_demand")


def _daily_regressor() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_depth=3, min_samples_leaf=20, l2_regularization=1.0, random_state=42
    )


def _train_daily_model(
    series_fn: Callable[[], Tuple[pd.DataFrame, pd.Timestamp]],
    model_name: str,
    filename: str,
    dataset: str,
    unit: str,
    simulated: bool = False,
) -> Dict[str, Any]:
    series, end = series_fn()
    sup = daily_supervised(series)
    folds = rolling_backtest(sup, end, _daily_regressor)
    if not folds:
        return {"status": "FAILED", "error": f"Insufficient history for {model_name}"}

    mae = float(np.mean([f["mae"] for f in folds]))
    base = float(np.mean([f["baseline_mae"] for f in folds]))
    pre_covid = [f for f in folds if not f["covid_period"]]
    metrics = {
        "target": f"average daily {unit} over the next {HORIZON_DAYS} days",
        "mae": round(mae, 3),
        "baseline_naive7_mae": round(base, 3),
        "wape_pct": round(float(np.mean([f["wape_pct"] for f in folds])), 2),
        "baseline_naive7_wape_pct": round(float(np.mean([f["baseline_wape_pct"] for f in folds])), 2),
        "skill_vs_naive7_pct": round((1 - mae / max(1e-9, base)) * 100, 1),
        "pre_covid_skill_pct": round((1 - np.mean([f["mae"] for f in pre_covid]) / max(1e-9, np.mean([f["baseline_mae"] for f in pre_covid]))) * 100, 1) if pre_covid else None,
        "beats_baseline": bool(mae < base),
        "split": f"rolling-origin backtest: {len(folds)} folds of 60 days",
        "test_period": f"{folds[0]['fold_start']} to {folds[-1]['fold_end']}",
        "folds": folds,
        "unit": unit,
        "simulated_data": simulated,
    }

    labelled = sup.dropna(subset=["target"])
    final = _daily_regressor().fit(labelled[DAILY_FEATURES], labelled["log_ratio_target"])
    # Champion/challenger: serve the model only if it beat the naive baseline across the backtest
    metrics["serving_method"] = "model" if metrics["beats_baseline"] else "baseline_naive7"
    artifact = {
        "model": final, "features": DAILY_FEATURES, "metrics": metrics, "version": "3.0.0",
        "trained_at": datetime.now().isoformat(), "type": "daily_forecaster", "data_through": str(end.date()),
        "serving_method": metrics["serving_method"],
    }
    path = register_model(model_name=model_name, version="3.0.0", dataset=dataset, features=DAILY_FEATURES,
                          metrics=metrics, model_obj=artifact, filename=filename)
    logger.info(f"{model_name}: backtest MAE {metrics['mae']} vs naive-7 {metrics['baseline_naive7_mae']} ({metrics['skill_vs_naive7_pct']}% skill)")
    return {"status": "SUCCESS", "model_name": model_name, "path": path, "metrics": metrics}


def train_lab_workload_model() -> Dict[str, Any]:
    """Model 4: next-7-day average daily test volume per laboratory category."""
    return _train_daily_model(lab_daily_series, "lab_workload_model", "lab_workload_model.joblib", "gold_laboratory", "tests")


def train_resource_demand_model() -> Dict[str, Any]:
    """Model 5: next-7-day average daily inpatient admissions across the network."""
    return _train_daily_model(admissions_daily_series, "resource_demand_model", "resource_demand_model.joblib", "gold_admissions", "admissions")


def train_outpatient_demand_model() -> Dict[str, Any]:
    """Model 7 (simulated operations data): next-7-day average daily outpatient demand per hospital."""
    return _train_daily_model(outpatient_daily_series, "outpatient_demand_model", "outpatient_demand_model.joblib",
                              "sim_outpatient_daily", "outpatient visits", simulated=True)


def train_drug_class_demand_model() -> Dict[str, Any]:
    """Model 8 (simulated operations data): next-7-day average daily units dispensed per drug class (network)."""
    return _train_daily_model(pharmacy_class_series, "drug_class_demand_model", "drug_class_demand_model.joblib",
                              "sim_pharmacy_daily", "units dispensed", simulated=True)


def _pharmacy_regressor() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson", max_iter=300, learning_rate=0.05, max_depth=4, min_samples_leaf=30, l2_regularization=1.0, random_state=42
    )


def train_pharmacy_demand_model() -> Dict[str, Any]:
    """Model 3: units dispensed per (site, medication) over the next 30 days."""
    end = pd.Timestamp(query_df_strict("SELECT max(prescription_date) AS d FROM gold_prescriptions").iloc[0]["d"])
    last_cutoff = end - pd.Timedelta(days=PHARMACY_HORIZON)
    cutoffs = [last_cutoff - pd.Timedelta(days=30 * k) for k in range(28)]
    frame = pharmacy_frame(cutoffs, end)
    frame = frame[(frame["u180"] > 0) | (frame["y30"] > 0)]

    test_cutoffs = sorted(cutoffs)[-3:]
    test = frame[frame["t"].isin(test_cutoffs)]
    train = frame[frame["t"] + pd.Timedelta(days=PHARMACY_HORIZON) <= min(test_cutoffs)]
    if len(train) < 200 or test.empty:
        return {"status": "FAILED", "error": "Insufficient dispensing history"}

    model = _pharmacy_regressor().fit(train[PHARMACY_FEATURES], train["y30"])
    y = test["y30"].to_numpy()
    pred = np.clip(model.predict(test[PHARMACY_FEATURES]), 0, None)
    scores = regression_scores(y, pred)
    naive30 = regression_scores(y, test["u30"].to_numpy())
    naive90 = regression_scores(y, (test["u90"] / 3).to_numpy())

    metrics = {
        "target": f"units dispensed per site and medication over the next {PHARMACY_HORIZON} days",
        "mae": scores["mae"],
        "wape_pct": scores["wape_pct"],
        "baseline_last30_mae": naive30["mae"],
        "baseline_last30_wape_pct": naive30["wape_pct"],
        "baseline_avg90_mae": naive90["mae"],
        "skill_vs_last30_pct": round((1 - scores["mae"] / max(1e-9, naive30["mae"])) * 100, 1),
        "beats_baseline": bool(scores["mae"] < naive30["mae"]),
        "split": "time-based: test = the 3 most recent monthly forecast dates",
        "test_period": f"{min(test_cutoffs).date()} to {max(test_cutoffs).date()}",
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "unit": "units",
        "assumption": "A prescription's recorded dispense count is spread evenly over its active period.",
    }

    labelled = frame[frame["t"] + pd.Timedelta(days=PHARMACY_HORIZON) <= end]
    final = _pharmacy_regressor().fit(labelled[PHARMACY_FEATURES], labelled["y30"])
    metrics["serving_method"] = "model" if metrics["beats_baseline"] else "baseline_last30"
    artifact = {
        "model": final, "features": PHARMACY_FEATURES, "metrics": metrics, "version": "2.0.0",
        "trained_at": datetime.now().isoformat(), "type": "pharmacy_demand_forecaster", "data_through": str(end.date()),
        "serving_method": metrics["serving_method"],
    }
    path = register_model(model_name="pharmacy_demand_model", version="2.0.0", dataset="gold_prescriptions",
                          features=PHARMACY_FEATURES, metrics=metrics, model_obj=artifact, filename="pharmacy_demand_model.joblib")
    logger.info(f"pharmacy_demand_model: MAE {metrics['mae']} vs last-30 {metrics['baseline_last30_mae']} ({metrics['skill_vs_last30_pct']}% skill)")
    return {"status": "SUCCESS", "model_name": "pharmacy_demand_model", "path": path, "metrics": metrics}


def train_all_models() -> Dict[str, Any]:
    """Train all 6 predictive models in sequence."""
    from src.ml.train_readmission import train_readmission_model
    from src.ml.train_los import train_los_model
    from src.ml.train_covid import train_covid_outcome_models

    return {
        "covid_outcomes": train_covid_outcome_models(),
        "readmission": train_readmission_model(),
        "los": train_los_model(),
        "pharmacy_demand": train_pharmacy_demand_model(),
        "lab_workload": train_lab_workload_model(),
        "resource_demand": train_resource_demand_model(),
        "outpatient_demand": train_outpatient_demand_model(),
        "drug_class_demand": train_drug_class_demand_model(),
    }


if __name__ == "__main__":
    train_all_models()
