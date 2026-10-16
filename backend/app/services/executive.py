"""Oncology outcomes services for the Executive workspace (analyst role; admins oversee)."""

from typing import List

import pandas as pd

from backend.app.schemas.operations import (
    CostByType,
    ExecutiveForecasts,
    ExecutiveKpis,
    ForecastMeta,
    ModelScore,
    StageMixRow,
    SurvivalCurve,
    SurvivalOverview,
    SurvivalPoint,
    SurvivalRow,
    TreatmentForecastRow,
    TrendPoint,
)
from backend.app.services.models import active_metrics
from src.ml.predict import forecast_treatment_demand
from src.utils.database import query_df_strict

TREATMENT_TYPES = ("Surgery", "Chemotherapy", "Immunotherapy", "Targeted therapy", "Radiation")
FORECAST_LABELS = {"Infusion": "Infusion chairs (chemo / immuno / targeted)", "Radiation": "Radiation sessions"}


def _round(v, nd=1):
    v = pd.to_numeric(v, errors="coerce")
    return None if v is None or v != v else round(float(v), nd)


def _cost_per_patient() -> pd.DataFrame:
    """Recorded cost of care per patient: surgical claims, visits and medicines."""
    return query_df_strict("""
        WITH c AS (
            SELECT patient_id, sum(total_amount) AS amt FROM gold_billing GROUP BY 1
            UNION ALL SELECT patient_id, sum(TRY_CAST(visit_cost AS DOUBLE)) FROM gold_appointments WHERE status = 'Completed' GROUP BY 1
            UNION ALL SELECT patient_id, sum(estimated_cost) FROM gold_prescriptions GROUP BY 1)
        SELECT patient_id, sum(amt) AS cost FROM c GROUP BY 1
    """)


def get_kpis() -> ExecutiveKpis:
    o = query_df_strict("""
        SELECT count(*) AS n, count(*) FILTER (WHERE is_deceased = 0) AS living,
               median(days_to_treatment) FILTER (WHERE days_to_treatment >= 0) AS ttt
        FROM gold_oncology_patients
    """).iloc[0]
    end = pd.Timestamp(query_df_strict("SELECT max(test_date) AS d FROM gold_laboratory").iloc[0]["d"])
    new_dx = query_df_strict("SELECT count(*) AS n FROM gold_oncology_patients WHERE CAST(diagnosis_date AS DATE) > CAST(? AS DATE) - INTERVAL 365 DAY",
                             [str(end.date())]).iloc[0]["n"]
    sessions = query_df_strict(
        f"SELECT count(*) AS n FROM gold_treatment_events WHERE event_type IN {TREATMENT_TYPES} AND CAST(event_date AS DATE) > CAST(? AS DATE) - INTERVAL 30 DAY",
        [str(end.date())]).iloc[0]["n"]
    five = query_df_strict("SELECT survival_pct FROM gold_survival WHERE group_type = 'all' AND month = 60")
    hospitals = query_df_strict("SELECT count(DISTINCT hospital_id) AS n FROM gold_treatment_events").iloc[0]["n"]
    return ExecutiveKpis(
        patients=int(o["n"]), living_patients=int(o["living"]), new_diagnoses_12m=int(new_dx),
        five_year_survival_pct=_round(five["survival_pct"].iloc[0]) if not five.empty else None,
        median_days_to_treatment=_round(o["ttt"], 0), treatment_sessions_30d=int(sessions),
        cost_of_care=round(float(_cost_per_patient()["cost"].sum()), 2), hospitals=int(hospitals),
        data_through=str(end.date()),
    )


def get_diagnoses_trend(months: int = 36) -> List[TrendPoint]:
    df = query_df_strict(f"""
        WITH end_d AS (SELECT max(CAST(test_date AS DATE)) AS d FROM gold_laboratory),
        dx AS (SELECT strftime(CAST(diagnosis_date AS DATE), '%Y-%m') AS m, count(*) AS n FROM gold_oncology_patients, end_d
               WHERE CAST(diagnosis_date AS DATE) > end_d.d - INTERVAL {int(months)} MONTH GROUP BY 1),
        dd AS (SELECT strftime(CAST(death_date AS DATE), '%Y-%m') AS m, count(*) AS n FROM gold_oncology_patients, end_d
               WHERE death_date IS NOT NULL AND CAST(death_date AS DATE) > end_d.d - INTERVAL {int(months)} MONTH GROUP BY 1)
        SELECT coalesce(dx.m, dd.m) AS month, coalesce(dx.n, 0) AS dx, coalesce(dd.n, 0) AS deaths
        FROM dx FULL OUTER JOIN dd ON dx.m = dd.m ORDER BY 1
    """)
    return [TrendPoint(period=r.month, value=float(r.dx), secondary=float(r.deaths)) for r in df.itertuples()]


def get_survival() -> SurvivalOverview:
    s = query_df_strict("SELECT group_type, group_label, patients, month, survival_pct, at_risk FROM gold_survival ORDER BY group_type, group_label, month")
    curves = []
    for (kind, label), g in s[s["group_type"].isin(["all", "stage", "cancer_type"])].groupby(["group_type", "group_label"], sort=False):
        g = g[g["month"] % 3 == 0]  # quarterly points are enough for a curve
        curves.append(SurvivalCurve(label=label, kind=kind, patients=int(g["patients"].iloc[0]),
                                    points=[SurvivalPoint(month=int(r.month), survival_pct=float(r.survival_pct), at_risk=int(r.at_risk)) for r in g.itertuples()]))
    at = s.set_index(["group_type", "group_label", "month"])["survival_pct"]

    def pick(kind, label, month):
        return _round(at.get((kind, label, month)))

    types = s[s["group_type"] == "cancer_type"].drop_duplicates("group_label")
    rows = [SurvivalRow(
        cancer_type=r.group_label, patients=int(r.patients),
        one_year_pct=pick("cancer_type", r.group_label, 12), three_year_pct=pick("cancer_type", r.group_label, 36),
        five_year_pct=pick("cancer_type", r.group_label, 60),
        stage_i_five_year_pct=pick("type_stage", f"{r.group_label} | Stage I", 60),
        stage_iv_five_year_pct=pick("type_stage", f"{r.group_label} | Stage IV", 60),
    ) for r in types.itertuples()]
    rows.sort(key=lambda r: -(r.five_year_pct or 0))
    return SurvivalOverview(curves=curves, by_type=rows,
                            note="Kaplan-Meier survival from the date of diagnosis; patients alive at the end of the data are censored.")


def get_stage_mix() -> List[StageMixRow]:
    df = query_df_strict("""
        SELECT cancer_type, count(*) FILTER (WHERE cancer_stage = 'I') AS s1, count(*) FILTER (WHERE cancer_stage = 'II') AS s2,
               count(*) FILTER (WHERE cancer_stage = 'III') AS s3, count(*) FILTER (WHERE cancer_stage = 'IV') AS s4
        FROM gold_oncology_patients GROUP BY 1 ORDER BY count(*) DESC
    """)
    return [StageMixRow(cancer_type=r.cancer_type, stage_i=int(r.s1), stage_ii=int(r.s2), stage_iii=int(r.s3), stage_iv=int(r.s4))
            for r in df.itertuples()]


def get_cost_by_type() -> List[CostByType]:
    onc = query_df_strict("SELECT patient_id, cancer_type FROM gold_oncology_patients")
    df = onc.merge(_cost_per_patient(), on="patient_id", how="left").fillna({"cost": 0.0})
    g = df.groupby("cancer_type").agg(patients=("patient_id", "count"), total=("cost", "sum")).reset_index().sort_values("total", ascending=False)
    return [CostByType(cancer_type=r.cancer_type, patients=int(r.patients), total_cost=round(float(r.total), 2),
                       cost_per_patient=round(float(r.total) / max(1, int(r.patients)), 2)) for r in g.itertuples()]


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
    m = active_metrics("outcome_risk_model").get("died_12m", {})
    if m:
        served = m.get("serving_method") == "stage_type_baseline"
        scores.append(ModelScore(
            model="Death within 12 months", purpose=f"Every living cancer patient · {m.get('total_positives')} deaths in the training year",
            primary_metric=f"ROC-AUC {m.get('roc_auc'):.2f} (model)",
            baseline=f"Stage + type {m.get('baseline_roc_auc_stage_type'):.2f} · age only {m.get('baseline_roc_auc_age_only'):.2f}",
            verdict="Baseline wins — baseline served" if served else _verdict(m.get("roc_auc"), m.get("baseline_roc_auc_stage_type")),
        ))
    for name, label, base_key in [
        ("treatment_demand_model", "Treatment sessions (7-day)", "baseline_naive7_mae"),
        ("lab_workload_model", "Lab workload (7-day)", "baseline_naive7_mae"),
        ("pharmacy_demand_model", "Stock-line demand (30-day)", "baseline_last30_mae"),
        ("outpatient_demand_model", "Outpatient demand (7-day) · simulated ops data", "baseline_naive7_mae"),
        ("drug_class_demand_model", "Drug-class demand (7-day) · simulated ops data", "baseline_naive7_mae"),
    ]:
        f = active_metrics(name)
        if f:
            method, served_label, served = served_forecast(f, base_key)
            scores.append(ModelScore(
                model=label, purpose=f"{f.get('split', 'Time-based holdout')} · {f.get('test_period', '')}",
                primary_metric=f"MAE {served:.2f} ({served_label.lower()})", baseline=f"Naive {f.get(base_key):.2f}",
                verdict=_verdict(served, f.get(base_key), higher_is_better=False) if not method.startswith("baseline") else "Baseline wins — baseline served",
            ))
    return scores


def get_forecasts() -> ExecutiveForecasts:
    f = forecast_treatment_demand()
    return ExecutiveForecasts(
        treatment=[TreatmentForecastRow(service=FORECAST_LABELS.get(r["group"], r["group"]), forecast_daily=r["forecast_daily"],
                                        last_7d_daily=r["last_7d_daily"]) for r in f["forecasts"]],
        treatment_forecast=ForecastMeta(**{k: f.get(k) for k in ForecastMeta.model_fields}),
        models=get_model_scorecard(),
    )
