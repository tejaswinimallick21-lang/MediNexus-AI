"""Laboratory Operations services (hcp role)."""

from typing import List, Optional

from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.schemas.operations import (
    CategoryWorkload,
    CriticalAlert,
    ForecastMeta,
    LabCapacityPlan,
    LabKpis,
    TrendPoint,
)
from src.ml.predict import forecast_lab_workload
from src.prescriptive.laboratory_rules import get_laboratory_prescriptive_plan
from src.utils.database import query_df_strict


def get_kpis() -> LabKpis:
    r = query_df_strict("""
        SELECT COUNT(*) AS total, SUM(is_abnormal) AS abnormal, SUM(is_critical) AS critical,
               COUNT(*) FILTER (WHERE CAST(test_date AS DATE) > (SELECT max(CAST(test_date AS DATE)) FROM gold_laboratory) - INTERVAL 30 DAY) AS last30
        FROM gold_laboratory
    """).iloc[0]
    total = int(r["total"])
    return LabKpis(
        total_tests=total,
        abnormal_tests=int(r["abnormal"] or 0),
        critical_tests=int(r["critical"] or 0),
        abnormal_pct=round(int(r["abnormal"] or 0) / max(1, total) * 100, 1),
        critical_pct=round(int(r["critical"] or 0) / max(1, total) * 100, 1),
        tests_last_30d=int(r["last30"] or 0),
    )


def get_workload_by_category() -> List[CategoryWorkload]:
    df = query_df_strict("""
        SELECT test_category AS category, COUNT(*) AS total, SUM(is_abnormal) AS abnormal, SUM(is_critical) AS critical
        FROM gold_laboratory WHERE test_category IS NOT NULL GROUP BY 1 ORDER BY total DESC
    """)
    return [CategoryWorkload(category=r.category, total=int(r.total), abnormal=int(r.abnormal), critical=int(r.critical)) for r in df.itertuples()]


def get_daily_volume(days: int = 180) -> List[TrendPoint]:
    df = query_df_strict(f"""
        WITH end_d AS (SELECT max(CAST(test_date AS DATE)) AS d FROM gold_laboratory)
        SELECT CAST(test_date AS DATE) AS day, COUNT(*) AS n, SUM(is_critical) AS crit
        FROM gold_laboratory, end_d WHERE CAST(test_date AS DATE) > end_d.d - INTERVAL {int(days)} DAY
        GROUP BY 1 ORDER BY 1
    """)
    return [TrendPoint(period=str(r.day.date() if hasattr(r.day, "date") else r.day), value=float(r.n), secondary=float(r.crit)) for r in df.itertuples()]


def get_categories() -> List[str]:
    df = query_df_strict("SELECT DISTINCT test_category AS c FROM gold_laboratory WHERE test_category IS NOT NULL ORDER BY c")
    return [str(c) for c in df["c"]]


def list_critical_alerts(params: PageParams, category: Optional[str] = None) -> Page[CriticalAlert]:
    where, args = "is_critical = 1", []
    if category:
        where += " AND test_category = ?"
        args.append(category)
    df = query_df_strict(
        f"""
        SELECT lab_id, patient_id, test_name, test_value, unit, reference_range, test_date, department_name
        FROM gold_laboratory WHERE {where}
        ORDER BY test_date DESC, lab_id DESC LIMIT ? OFFSET ?
        """,
        args + [params.limit + 1, params.offset],
    )
    rows = [
        CriticalAlert(
            lab_id=r.lab_id, patient_id=r.patient_id, test_name=r.test_name,
            test_value=None if r.test_value != r.test_value else round(float(r.test_value), 2),
            unit=r.unit if isinstance(r.unit, str) and r.unit != "standard" else None,  # "standard" = imputed placeholder
            reference_range=r.reference_range if isinstance(r.reference_range, str) else None,
            test_date=str(r.test_date),
            department_name=r.department_name if isinstance(r.department_name, str) else None,
        )
        for r in df.itertuples()
    ]
    return build_page(rows, params)


def get_capacity_plan(category: str) -> LabCapacityPlan:
    if category not in get_categories():
        raise APIError(404, "unknown_category", f"No laboratory category named '{category}'.")
    forecast = forecast_lab_workload()
    row = next((f for f in forecast["forecasts"] if f["group"] == category), None)
    projected = row["forecast_daily"] if row else 0.0
    # Bench capacity is not recorded in the data: estimate a typical busy day (75th-percentile daily volume over the
    # past year) plus 25% headroom. The 95th percentile would be dominated by rare peak days.
    stats = query_df_strict("""
        WITH end_d AS (SELECT max(CAST(test_date AS DATE)) AS d FROM gold_laboratory),
        daily AS (
            SELECT CAST(test_date AS DATE) AS day, COUNT(*) AS n FROM gold_laboratory, end_d
            WHERE test_category = ? AND CAST(test_date AS DATE) > end_d.d - INTERVAL 365 DAY GROUP BY 1)
        SELECT (SELECT quantile_cont(n, 0.75) FROM daily) AS p75,
               (SELECT AVG(is_critical) * 100 FROM gold_laboratory WHERE test_category = ?) AS crit_rate
    """, [category, category]).iloc[0]
    capacity = max(1, int(round(float(stats["p75"] or 0) * 1.25)))
    plan = get_laboratory_prescriptive_plan(
        category=category,
        projected_daily_tests=int(round(projected)),
        critical_rate_pct=round(float(stats["crit_rate"] or 0), 1),
        current_capacity=capacity,
    )
    return LabCapacityPlan(
        category=category,
        forecast_daily_tests=projected,
        last_7d_daily=row["last_7d_daily"] if row else 0.0,
        estimated_capacity_daily=capacity,
        utilization_pct=plan["utilization_percentage"],
        critical_rate_pct=round(float(stats["crit_rate"] or 0), 1),
        operational_status=plan["operational_status"],
        actions=plan["recommended_staffing_actions"],
        assessment=plan["analyzer_capacity_assessment"] + " Capacity is estimated (75th-percentile daily volume over the past year + 25% headroom).",
        forecast=ForecastMeta(**{k: forecast.get(k) for k in ForecastMeta.model_fields}),
    )
