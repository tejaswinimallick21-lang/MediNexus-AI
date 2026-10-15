"""
Analyst Command Center services (analyst role; admins oversee).

- What-if capacity simulation: replays the outpatient queue over a historical window of the
  SIMULATED operations data (sim_outpatient_daily, sim_staff_roster) with changed staffing or demand.
- Readmission economics: facts from Gold admissions/billing plus the readmission model's held-out
  performance; the programme scenario itself is computed in the browser from these facts.
- Model monitor: every active model in the registry with its out-of-sample score against a baseline.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.app.core.errors import APIError
from backend.app.schemas.command import (
    HospitalOption,
    ModelMonitorRow,
    ReadmissionEconomics,
    WhatIfDay,
    WhatIfIn,
    WhatIfResult,
    WhatIfSide,
)
from backend.app.services.executive import _verdict, served_forecast
from src.utils.database import query_df_strict

ABANDON_RATE = 0.10  # share of the waiting list that drops out each day (same rule as the simulator)
SHIFT_HOURS = 8.0
OVERTIME_MULTIPLIER = 1.5


# ---- What-if capacity simulation --------------------------------------------------------------

def list_hospitals() -> List[HospitalOption]:
    """Hospitals ordered by access pressure (lowest share of demand served first)."""
    df = query_df_strict("""
        SELECT p.hospital_id, p.hospital_name, p.beds, p.physicians,
               AVG(o.demand) AS demand, SUM(o.served) / NULLIF(SUM(o.demand), 0) * 100 AS served_pct, AVG(o.avg_wait_days) AS wait
        FROM sim_hospital_profile p JOIN sim_outpatient_daily o USING (hospital_id)
        WHERE CAST(o.date AS DATE) > (SELECT max(CAST(date AS DATE)) FROM sim_outpatient_daily) - INTERVAL 365 DAY
        GROUP BY 1, 2, 3, 4 ORDER BY served_pct ASC, demand DESC
    """)
    return [
        HospitalOption(
            hospital_id=r.hospital_id, hospital_name=r.hospital_name, beds=int(r.beds), physicians=int(r.physicians),
            avg_daily_demand=round(float(r.demand), 1), served_pct=round(float(r.served_pct or 0), 1), avg_wait_days=round(float(r.wait or 0), 2),
        )
        for r in df.itertuples()
    ]


def _window(period: str) -> Tuple[str, str]:
    end = pd.Timestamp(query_df_strict("SELECT max(CAST(date AS DATE)) AS d FROM sim_outpatient_daily").iloc[0]["d"]).strftime("%Y-%m-%d")
    days = 90 if period == "last_90" else 365
    start = (pd.Timestamp(end) - pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    return start, end


def _replay(demand: np.ndarray, capacity: np.ndarray, carry0: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Queue replay per hospital (rows) over days (columns): returns served, backlog and abandoned."""
    served, backlog, lost = (np.zeros_like(demand, dtype=float) for _ in range(3))
    carry = carry0.astype(float)
    for d in range(demand.shape[1]):
        want = demand[:, d] + carry
        served[:, d] = np.minimum(want, capacity[:, d])
        unmet = want - served[:, d]
        lost[:, d] = unmet * ABANDON_RATE
        carry = unmet * (1 - ABANDON_RATE)
        backlog[:, d] = carry
    return served, backlog, lost


def _side(demand, capacity, served, backlog, lost, docs, revenue_per_visit, cost) -> WhatIfSide:
    day_served, day_backlog = served.sum(axis=0), backlog.sum(axis=0)
    wait = np.where(day_served > 0, day_backlog / np.maximum(day_served, 1), np.nan)
    return WhatIfSide(
        demand=int(round(demand.sum())),
        served=int(round(served.sum())),
        lost_to_follow_up=int(round(lost.sum())),
        avg_backlog=round(float(day_backlog.mean()), 1),
        avg_wait_days=round(float(np.nanmean(wait)), 2),
        utilization_pct=round(float(served.sum() / max(1.0, capacity.sum()) * 100), 1),
        visits_per_physician_day=round(float(served.sum() / max(1.0, docs.sum())), 1),
        revenue=round(float((served * revenue_per_visit[:, None]).sum()), 2),
        staffing_cost=round(float(cost), 2),
    )


def _pct(new: float, old: float) -> float:
    return (new - old) / old * 100 if old else 0.0


def run_what_if(body: WhatIfIn) -> WhatIfResult:
    start, end = _window(body.period)
    where, params = "", [start, end]
    if body.hospital_id:
        where, params = "AND o.hospital_id = ?", params + [body.hospital_id]
    df = query_df_strict(f"""
        SELECT o.date, o.hospital_id, o.hospital_name, o.demand, o.capacity, o.physicians_on_duty
        FROM sim_outpatient_daily o
        WHERE CAST(o.date AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) {where}
        ORDER BY o.hospital_id, o.date
    """, params)
    if df.empty:
        raise APIError(404, "hospital_not_found", "No simulated outpatient data for that hospital.")
    hospital_ids = sorted(df["hospital_id"].unique())
    carry_df = query_df_strict(f"""
        SELECT hospital_id, backlog FROM sim_outpatient_daily o
        WHERE CAST(date AS DATE) = CAST(? AS DATE) - INTERVAL 1 DAY {where}
    """, [start] + params[2:])
    roster = query_df_strict("""
        SELECT r.hospital_id, SUM(r.physicians * r.visits_per_physician_day * r.revenue_per_visit) / SUM(r.physicians * r.visits_per_physician_day) AS rev,
               SUM(r.physicians * r.cost_per_physician_hour) / SUM(r.physicians) AS cost_hr,
               SUM(r.physicians * r.visits_per_physician_day) / SUM(r.physicians) AS vpd,
               max(p.physicians) AS physicians
        FROM sim_staff_roster r JOIN sim_hospital_profile p USING (hospital_id) GROUP BY 1
    """).set_index("hospital_id").reindex(hospital_ids)

    def grid(col: str) -> np.ndarray:
        return df.pivot(index="hospital_id", columns="date", values=col).reindex(hospital_ids).fillna(0).to_numpy(dtype=float)

    demand, capacity, on_duty = grid("demand"), grid("capacity"), grid("physicians_on_duty")
    dates = sorted(df["date"].unique())
    carry0 = carry_df.set_index("hospital_id")["backlog"].reindex(hospital_ids).fillna(0).to_numpy(dtype=float)
    rev, cost_hr = roster["rev"].to_numpy(dtype=float), roster["cost_hr"].to_numpy(dtype=float)
    vpd, physicians = roster["vpd"].to_numpy(dtype=float), roster["physicians"].to_numpy(dtype=float)

    # Scenario: added physicians follow the same duty pattern; extra visits scale each doctor's daily throughput
    rate = np.where(on_duty > 0, capacity / np.maximum(on_duty, 1), 0)
    docs = on_duty + body.extra_physicians * on_duty / physicians[:, None]
    s_capacity = docs * rate * (1 + body.extra_visits_per_physician / vpd[:, None])
    s_demand = demand * (1 + body.demand_change_pct / 100)

    base = _replay(demand, capacity, carry0)
    scen = _replay(s_demand, s_capacity, carry0)
    base_cost = float((on_duty * SHIFT_HOURS * cost_hr[:, None]).sum())
    overtime = on_duty * body.extra_visits_per_physician * (SHIFT_HOURS / vpd[:, None]) * cost_hr[:, None] * OVERTIME_MULTIPLIER
    scen_cost = float((docs * SHIFT_HOURS * cost_hr[:, None]).sum() + overtime.sum())

    b = _side(demand, capacity, *base, on_duty, rev, base_cost)
    s = _side(s_demand, s_capacity, *scen, docs, rev, scen_cost)
    n_days = len(dates)
    net = (s.revenue - b.revenue) - (s.staffing_cost - b.staffing_cost)

    insights: List[str] = []
    if b.avg_backlog > 0 or s.avg_backlog > 0:
        insights.append(
            f"Average waiting list moves from {b.avg_backlog:,.0f} to {s.avg_backlog:,.0f} patients ({_pct(s.avg_backlog, b.avg_backlog):+.0f}%); "
            f"average wait from {b.avg_wait_days:.2f} to {s.avg_wait_days:.2f} days."
        )
    insights.append(
        f"Patients lost to follow-up (leave the waiting list): {b.lost_to_follow_up:,} → {s.lost_to_follow_up:,} over {n_days} days."
    )
    load_change = _pct(s.visits_per_physician_day, b.visits_per_physician_day)
    insights.append(f"Visits per on-duty physician per day: {b.visits_per_physician_day:.1f} → {s.visits_per_physician_day:.1f} ({load_change:+.0f}%).")
    if load_change > 15:
        insights.append("Physician load rises by more than 15%. Plan rota or overtime cover; this simulation assumes no drop in throughput from fatigue.")
    if s.utilization_pct < 80:
        insights.append(f"Capacity outpaces demand: clinic utilization falls to {s.utilization_pct:.0f}%, so part of the added staffing cost buys idle time.")
    if not body.hospital_id:
        hot = int((base[0].sum(axis=1) / np.maximum(capacity.sum(axis=1), 1) >= 0.97).sum())
        insights.append(f"{hot} of {len(hospital_ids)} hospitals run at 97%+ clinic utilization in this period; capacity added elsewhere mostly adds cost. Target those sites first.")
    insights.append(f"Net financial impact over the period: {'+' if net >= 0 else '−'}${abs(net):,.0f} (revenue change minus staffing change).")

    scope = str(df["hospital_name"].iloc[0]) if body.hospital_id else f"All {len(hospital_ids)} hospitals"
    return WhatIfResult(
        simulated_data=True,
        scope=scope,
        period_start=start,
        period_end=end,
        days=n_days,
        baseline=b,
        scenario=s,
        net_impact=round(net, 2),
        net_impact_per_month=round(net / n_days * 30, 2),
        insights=insights,
        assumptions=[
            "Simulated operations data (sim_outpatient_daily, sim_staff_roster); not source records.",
            f"{int(ABANDON_RATE * 100)}% of the waiting list drops out each day.",
            "Revenue per visit and physician hourly cost come from each hospital's simulated staff roster.",
            f"Extra visits are paid as overtime at {OVERTIME_MULTIPLIER}× the hourly rate; added physicians work {SHIFT_HOURS:.0f}-hour shifts on the same duty pattern.",
            "Clinical quality and fatigue effects are not modelled.",
        ],
        daily=[
            WhatIfDay(date=str(d), baseline_backlog=round(float(base[1][:, i].sum()), 1), scenario_backlog=round(float(scen[1][:, i].sum()), 1),
                      baseline_served=round(float(base[0][:, i].sum()), 1), scenario_served=round(float(scen[0][:, i].sum()), 1))
            for i, d in enumerate(dates)
        ],
    )


# ---- Readmission economics --------------------------------------------------------------------

def _metrics(model_name: str) -> Tuple[Optional[Dict], Optional[str], Optional[str], int]:
    df = query_df_strict(
        "SELECT version, training_timestamp, metrics, status FROM model_registry WHERE model_name = ? ORDER BY training_timestamp DESC",
        [model_name],
    )
    active = df[df["status"] == "ACTIVE"]
    if active.empty:
        return None, None, None, len(df)
    row = active.iloc[0]
    raw = row["metrics"]
    return (json.loads(raw) if isinstance(raw, str) else dict(raw)), str(row["version"]), str(row["training_timestamp"]), len(df)


def get_readmission_economics() -> ReadmissionEconomics:
    a = query_df_strict("""
        WITH end_d AS (SELECT max(CAST(admission_date AS DATE)) AS d FROM gold_admissions)
        SELECT min(CAST(admission_date AS DATE)) AS start_d, max(CAST(admission_date AS DATE)) AS end_d,
               COUNT(*) AS n, SUM(readmitted_30d) AS readm, AVG(length_of_stay_days) AS los
        FROM gold_admissions, end_d WHERE CAST(admission_date AS DATE) > end_d.d - INTERVAL 365 DAY
    """).iloc[0]
    cost = query_df_strict("""
        WITH end_d AS (SELECT max(CAST(admission_date AS DATE)) AS d FROM gold_admissions)
        SELECT AVG(b.total_amount) AS c FROM gold_billing b JOIN gold_admissions g USING (admission_id), end_d
        WHERE CAST(g.admission_date AS DATE) > end_d.d - INTERVAL 365 DAY
    """).iloc[0]["c"]
    m, _, _, _ = _metrics("readmission_risk_model")
    if not m:
        raise APIError(503, "model_unavailable", "The readmission model has not been trained yet.")
    (tn, fp), (fn, tp) = m["confusion_matrix"]
    n_test = tn + fp + fn + tp
    n, readm = int(a["n"]), int(a["readm"] or 0)
    return ReadmissionEconomics(
        period_start=str(a["start_d"])[:10],
        period_end=str(a["end_d"])[:10],
        discharges=n,
        unplanned_readmissions=readm,
        readmission_rate_pct=round(readm / max(1, n) * 100, 2),
        avg_cost_per_stay=round(float(cost or 0), 2),
        avg_los_days=round(float(a["los"] or 0), 1),
        model_roc_auc=float(m["roc_auc"]),
        model_flag_share_pct=round((fp + tp) / max(1, n_test) * 100, 1),
        model_capture_pct=round(float(m["recall"]) * 100, 1),
        model_precision_pct=round(float(m["precision"]) * 100, 1),
        model_test_positives=int(m["test_positives"]),
        default_effectiveness_pct=20.0,
        default_cost_per_enrolled=150.0,
        notes=[
            "Cost of a readmission stay is the average billed amount per inpatient stay in the same 12 months.",
            f"Model capture and flag rates are held-out estimates from only {int(m['test_positives'])} readmissions, so they carry wide uncertainty.",
            "Programme effectiveness and cost per enrolled patient are planning assumptions; adjust them to your programme.",
        ],
    )


# ---- Model monitor ----------------------------------------------------------------------------

MONITORED = [  # registry name, label
    ("readmission_risk_model", "Unplanned 30-day readmission"),
    ("outcome_risk_model", "12-month outcome risk"),
    ("length_of_stay_model", "Length of stay"),
    ("outpatient_demand_model", "Outpatient demand (7-day)"),
    ("drug_class_demand_model", "Drug-class demand (7-day)"),
    ("resource_demand_model", "Admission demand (7-day)"),
    ("lab_workload_model", "Lab workload (7-day)"),
    ("pharmacy_demand_model", "Stock-line demand (30-day)"),
]


def _age_days(ts: str) -> int:
    try:
        return max(0, (datetime.now() - pd.Timestamp(ts).to_pydatetime()).days)
    except (ValueError, TypeError):
        return 0


def list_model_monitor() -> List[ModelMonitorRow]:
    rows: List[ModelMonitorRow] = []
    for name, label in MONITORED:
        m, version, trained_at, versions = _metrics(name)
        if not m:
            continue
        source = "Simulated ops data" if m.get("simulated_data") else "Synthea"
        common = dict(model_name=name, label=label, version=version, trained_at=trained_at[:19], age_days=_age_days(trained_at),
                      data_source=source, versions=versions)
        if name == "readmission_risk_model":
            verdict = _verdict(m.get("roc_auc"), m.get("baseline_roc_auc_age_los"))
            low = int(m.get("test_positives", 0)) < 50
            rows.append(ModelMonitorRow(
                **common, primary_metric=f"ROC-AUC {m['roc_auc']:.2f} · recall {m['recall'] * 100:.0f}%",
                baseline=f"Age + LOS {m['baseline_roc_auc_age_los']:.2f}", verdict=verdict, serving="Model",
                health="low_evidence" if low else "healthy",
                note=f"{m.get('test_positives')} readmissions in the held-out set; precision {m['precision'] * 100:.1f}%.",
            ))
        elif name == "outcome_risk_model":
            h, d = m.get("hospitalized_12m", {}), m.get("died_12m", {})
            rows.append(ModelMonitorRow(
                **common, primary_metric=f"Admission AUC {h.get('roc_auc', 0):.2f} · mortality AUC {d.get('roc_auc', 0):.2f}",
                baseline=f"Age only {h.get('baseline_roc_auc_age_only', 0):.2f} / {d.get('baseline_roc_auc_age_only', 0):.2f}",
                verdict=_verdict(h.get("roc_auc"), h.get("baseline_roc_auc_age_only")), serving="Model", health="healthy",
                note="Trained on history up to one year before the end of the data; scored on all history.",
            ))
        elif name == "length_of_stay_model":
            rows.append(ModelMonitorRow(
                **common, primary_metric=f"MAE {m['mae_days']:.2f} days", baseline=f"Median {m['baseline_mae_days_median']:.2f} days",
                verdict=_verdict(m["mae_days"], m["baseline_mae_days_median"], higher_is_better=False), serving="Model", health="healthy",
                note=f"R² {m.get('r2_score', 0):.2f} on {m.get('test_samples')} held-out stays.",
            ))
        else:
            base_key = "baseline_last30_mae" if "baseline_last30_mae" in m else "baseline_naive7_mae"
            method, served_label, served = served_forecast(m, base_key)
            baseline_served = method.startswith("baseline")
            tried = f"gradient-boosting model MAE {m['mae']:.2f}" + (f", surge-aware {m['surge_aware_mae']:.2f}" if "surge_aware_mae" in m else "")
            rows.append(ModelMonitorRow(
                **common, primary_metric=f"MAE {served:.2f} ({served_label.lower()})", baseline=f"Naive {m[base_key]:.2f}",
                verdict="Baseline wins — baseline served" if baseline_served else _verdict(served, m[base_key], higher_is_better=False),
                serving=served_label, health="baseline" if baseline_served else "healthy",
                note=f"{m.get('split', 'Time-based holdout')} · {m.get('test_period', '')} · tried: {tried}",
            ))
    return rows
