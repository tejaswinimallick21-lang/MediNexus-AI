"""
Operational forecasters: the surge-aware method, and champion/challenger serving the most
accurate method from the backtest.
"""

import numpy as np

from src.ml.forecasting import SURGE_THRESHOLD, surge_aware
from src.ml.model_registry import load_model
from src.ml.predict import forecast_lab_workload, forecast_treatment_demand


def test_surge_aware_blends_when_stable_and_follows_a_surge():
    stable = surge_aware([10.0], [12.0])  # small shift -> 7/28-day blend
    assert stable[0] == 11.0
    surge = surge_aware([40.0], [10.0])  # 4x jump -> follow the 7-day average
    assert surge[0] == 40.0
    edge = np.expm1(np.log1p(10.0) + SURGE_THRESHOLD * 0.99)  # just under the threshold -> still blended
    assert surge_aware([edge], [10.0])[0] == 0.5 * edge + 5.0


def test_served_method_is_the_most_accurate_in_the_backtest():
    for name in ("lab_workload_model", "treatment_demand_model", "outpatient_demand_model", "drug_class_demand_model"):
        m = load_model(name)["metrics"]
        candidates = {"model": m["mae"], "surge_aware": m["surge_aware_mae"], "baseline_naive7": m["baseline_naive7_mae"]}
        assert m["serving_method"] == min(candidates, key=candidates.get), name
        assert m["served_mae"] == round(candidates[m["serving_method"]], 3)
        assert m["served_mae"] <= m["baseline_naive7_mae"]  # never serve something worse than the baseline


def test_forecasts_report_the_served_method():
    for f in (forecast_lab_workload(), forecast_treatment_demand()):
        assert f["serving_method"] in {"model", "surge_aware", "baseline_naive7"}
        assert f["holdout_served_mae"] is not None and f["holdout_served_mae"] <= f["holdout_baseline_mae"]
        assert all(r["forecast_daily"] >= 0 for r in f["forecasts"])
