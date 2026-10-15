"""Executive Operations services (analyst role; admins oversee)."""

from typing import List

from backend.app.schemas.operations import (
    CapacityPlan,
    ExecutiveForecasts,
    ExecutiveKpis,
    ForecastMeta,
    ModelScore,
    ReadmissionBreakdownRow,
    ReadmissionDrivers,
    RevenueByDepartment,
    TrendPoint,
)
from backend.app.services.models import active_metrics
from src.analytics.diagnostic import diagnose_readmissions
from src.ml.predict import forecast_admissions
from src.prescriptive.hospital_rules import get_hospital_capacity_plan
from src.utils.database import query_df_strict

RECENT_DAYS = 90  # occupancy is reported over the most recent window of data, not all history


def get_kpis() -> ExecutiveKpis:
    a = query_df_strict("""
        SELECT COUNT(*) AS adm, COUNT(DISTINCT patient_id) AS pts, AVG(readmitted_30d) * 100 AS readm,
               AVG(length_of_stay_days) AS los, COUNT(DISTINCT hospital_id) AS hospitals, max(admission_date) AS end_d
        FROM gold_admissions
    """).iloc[0]
    b = query_df_strict("SELECT SUM(total_amount) AS rev, SUM(patient_payable) AS due FROM gold_billing").iloc[0]
    occ = query_df_strict(f"""
        SELECT AVG(estimated_occupancy_rate) * 100 AS occ FROM gold_hospital_operations
        WHERE CAST(admission_date AS DATE) > (SELECT max(CAST(admission_date AS DATE)) FROM gold_hospital_operations) - INTERVAL {RECENT_DAYS} DAY
    """).iloc[0]["occ"]
    rev, due = float(b["rev"] or 0), float(b["due"] or 0)
    return ExecutiveKpis(
        total_admissions=int(a["adm"]),
        patients_admitted=int(a["pts"]),
        unplanned_readmission_rate_pct=round(float(a["readm"] or 0), 2),
        average_los_days=round(float(a["los"] or 0), 1),
        occupancy_rate_pct=None if occ is None or occ != occ else round(float(occ), 1),
        total_revenue=round(rev, 2),
        collection_rate_pct=round((rev - due) / max(1.0, rev) * 100, 1),
        hospitals=int(a["hospitals"]),
        data_through=str(a["end_d"]),
    )


def get_admissions_trend(months: int = 36) -> List[TrendPoint]:
    df = query_df_strict(f"""
        WITH end_d AS (SELECT max(CAST(admission_date AS DATE)) AS d FROM gold_admissions)
        SELECT strftime(CAST(admission_date AS DATE), '%Y-%m') AS month, COUNT(*) AS adm, SUM(readmitted_30d) AS readm
        FROM gold_admissions, end_d
        WHERE CAST(admission_date AS DATE) > end_d.d - INTERVAL {int(months)} MONTH
        GROUP BY 1 ORDER BY 1
    """)
    return [TrendPoint(period=r.month, value=float(r.adm), secondary=float(r.readm or 0)) for r in df.itertuples()]


def get_revenue_by_department() -> List[RevenueByDepartment]:
    df = query_df_strict("""
        SELECT coalesce(department_name, 'Unassigned') AS dept, SUM(total_amount) AS rev, COUNT(*) AS n
        FROM gold_billing GROUP BY 1 ORDER BY rev DESC
    """)
    return [RevenueByDepartment(department=r.dept, revenue=round(float(r.rev or 0), 2), admissions=int(r.n)) for r in df.itertuples()]


SERVED_LABELS = {"model": "Model", "surge_aware": "Surge-aware average", "baseline_naive7": "Naive baseline", "baseline_last30": "Naive baseline"}


def served_forecast(m: dict, base_key: str):
    """(method key, its display name, its backtest MAE) for the forecasting method actually served."""
    method = m.get("serving_method", "model")
    mae = m.get("served_mae", m.get("mae") if method == "model" else m.get(base_key))
    return method, SERVED_LABELS.get(method, method), mae


def _verdict(score: float, baseline: float, higher_is_better: bool = True) -> str:
    if score is None or baseline is None:
        return "Not evaluated"
    lift = (score - baseline) if higher_is_better else (baseline - score)
    if lift > 0.02 * (abs(baseline) or 1):
        return "Beats baseline"
    if lift >= 0:
        return "Marginal over baseline"
    return "Baseline wins — baseline served"


def get_model_scorecard() -> List[ModelScore]:
    scores: List[ModelScore] = []
    outlook = active_metrics("outcome_risk_model")
    for key, label in [("hospitalized_12m", "Hospital admission within 12 months"), ("died_12m", "Death within 12 months")]:
        m = outlook.get(key, {})
        if m:
            scores.append(ModelScore(
                model=label, purpose="Risk at diagnosis (pre-diagnosis history only)",
                primary_metric=f"ROC-AUC {m.get('roc_auc'):.2f}", baseline=f"Age only {m.get('baseline_roc_auc_age_only'):.2f}",
                verdict=_verdict(m.get("roc_auc"), m.get("baseline_roc_auc_age_only")),
            ))
    r = active_metrics("readmission_risk_model")
    if r:
        scores.append(ModelScore(
            model="Unplanned 30-day readmission", purpose=f"Scored at discharge · {r.get('total_positives')} positive cases",
            primary_metric=f"ROC-AUC {r.get('roc_auc'):.2f} (CV {r.get('cv_roc_auc_mean'):.2f} ± {r.get('cv_roc_auc_std'):.2f})",
            baseline=f"Age + LOS {r.get('baseline_roc_auc_age_los'):.2f}",
            verdict=_verdict(r.get("roc_auc"), r.get("baseline_roc_auc_age_los")),
        ))
    los = active_metrics("length_of_stay_model")
    if los:
        scores.append(ModelScore(
            model="Length of stay", purpose="Scored at admission",
            primary_metric=f"MAE {los.get('mae_days'):.2f} days", baseline=f"Median {los.get('baseline_mae_days_median'):.2f} days",
            verdict=_verdict(los.get("mae_days"), los.get("baseline_mae_days_median"), higher_is_better=False),
        ))
    for name, label, base_key in [
        ("outpatient_demand_model", "Outpatient demand (7-day) · simulated ops data", "baseline_naive7_mae"),
        ("drug_class_demand_model", "Drug-class demand (7-day) · simulated ops data", "baseline_naive7_mae"),
        ("resource_demand_model", "Admission demand (7-day)", "baseline_naive7_mae"),
        ("lab_workload_model", "Lab workload (7-day)", "baseline_naive7_mae"),
        ("pharmacy_demand_model", "Stock-line demand (30-day)", "baseline_last30_mae"),
    ]:
        m = active_metrics(name)
        if m:
            method, served_label, served = served_forecast(m, base_key)
            scores.append(ModelScore(
                model=label, purpose=f"{m.get('split', 'Time-based holdout')} · {m.get('test_period', '')}",
                primary_metric=f"MAE {served:.2f} ({served_label.lower()})", baseline=f"Naive {m.get(base_key):.2f}",
                verdict=_verdict(served, m.get(base_key), higher_is_better=False) if not method.startswith("baseline") else "Baseline wins — baseline served",
            ))
    return scores


def get_forecasts() -> ExecutiveForecasts:
    f = forecast_admissions()
    row = f["forecasts"][0] if f["forecasts"] else {"forecast_daily": 0.0, "last_7d_daily": 0.0}
    return ExecutiveForecasts(
        admissions_next_7d_daily=row["forecast_daily"],
        admissions_last_7d_daily=row["last_7d_daily"],
        admissions_forecast=ForecastMeta(**{k: f.get(k) for k in ForecastMeta.model_fields}),
        models=get_model_scorecard(),
    )


def get_readmission_drivers() -> ReadmissionDrivers:
    d = diagnose_readmissions()
    return ReadmissionDrivers(
        summary=d["summary"],
        findings=d["associated_factors"],
        by_admission_type=[
            ReadmissionBreakdownRow(label=str(r["admission_type"]), count=int(r["count"]), rate_pct=float(r["readm_pct"] or 0))
            for r in d["by_admission_type"]
        ],
        by_reason=[
            ReadmissionBreakdownRow(label=str(r["admission_reason"]), count=int(r["count"]), rate_pct=float(r["readm_pct"] or 0))
            for r in d.get("by_admission_reason", [])
        ][:10],
    )


def get_capacity_plan() -> CapacityPlan:
    kpis = get_kpis()
    forecast = get_forecasts()
    occupancy = (kpis.occupancy_rate_pct or 0) / 100.0
    plan = get_hospital_capacity_plan(
        occupancy_rate=occupancy,
        projected_daily_admissions=int(round(forecast.admissions_next_7d_daily)),
        average_los=kpis.average_los_days,
    )
    return CapacityPlan(
        surge_tier=plan["surge_tier"],
        occupancy_pct=kpis.occupancy_rate_pct,
        projected_daily_admissions=forecast.admissions_next_7d_daily,
        average_los_days=kpis.average_los_days,
        directives=plan["action_directives"],
        assessment=plan["throughput_assessment"],
        occupancy_note=f"Average over the last {RECENT_DAYS} days of data; bed capacity is estimated (1.25 × each unit's peak census).",
    )
