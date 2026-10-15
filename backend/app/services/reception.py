"""
Patient Access services (/api/reception/*, analyst role): outpatient volumes, attendance,
waiting-room performance and the appointment log.

Minimum necessary: operations analysts never receive patient names, contact details, diagnoses
or visit reasons. Rows carry a pseudonymous patient ID; with Synthea data the raw
`reason_for_visit` is clinical (e.g. "Hypertension"), so only the non-clinical visit type is returned.
"""

from typing import List, Optional

from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.schemas.common import LabelCount
from backend.app.schemas.reception import (
    AppointmentRow,
    HourlyWait,
    ReceptionFilters,
    ReceptionKpis,
    StatusDistribution,
    WaitInsights,
)
from src.utils.database import query_df_strict

WAIT_TARGET_MINUTES = 20
VISIT_TYPE_LABELS = {"wellness": "Wellness visit", "ambulatory": "Ambulatory visit", "outpatient": "Outpatient visit"}


def get_kpis() -> ReceptionKpis:
    row = query_df_strict("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'Completed') AS completed,
               COUNT(*) FILTER (WHERE status = 'No-Show') AS no_shows,
               COUNT(*) FILTER (WHERE status = 'Cancelled') AS cancelled,
               AVG(waiting_time_minutes) FILTER (WHERE status = 'Completed') AS avg_wait
        FROM gold_appointments
    """).iloc[0]
    total = int(row["total"])
    return ReceptionKpis(
        total_appointments=total,
        completed=int(row["completed"]),
        no_shows=int(row["no_shows"]),
        cancelled=int(row["cancelled"]),
        no_show_rate_pct=round(int(row["no_shows"]) / max(1, total) * 100, 1),
        cancellation_rate_pct=round(int(row["cancelled"]) / max(1, total) * 100, 1),
        avg_wait_minutes=round(float(row["avg_wait"] or 0.0), 1),
    )


def get_status_distribution() -> StatusDistribution:
    df = query_df_strict("SELECT status, COUNT(*) AS n FROM gold_appointments GROUP BY status ORDER BY n DESC")
    return StatusDistribution(items=[LabelCount(label=r.status, count=int(r.n)) for r in df.itertuples()])


def get_wait_insights() -> WaitInsights:
    """Hourly arrival volume and average wait for completed visits, with findings computed from the data."""
    df = query_df_strict("""
        SELECT SUBSTR(appointment_time, 1, 2) AS hour, COUNT(*) AS volume, ROUND(AVG(waiting_time_minutes), 1) AS avg_wait
        FROM gold_appointments
        WHERE status = 'Completed' AND appointment_time IS NOT NULL
        GROUP BY hour ORDER BY hour
    """)
    by_hour = [HourlyWait(hour=r.hour, volume=int(r.volume), avg_wait_min=float(r.avg_wait)) for r in df.itertuples()]
    findings: List[str] = []
    if by_hour:
        busiest = max(by_hour, key=lambda h: h.volume)
        slowest = max(by_hour, key=lambda h: h.avg_wait_min)
        spread = slowest.avg_wait_min - min(h.avg_wait_min for h in by_hour)
        findings.append(f"Busiest arrival hour: {busiest.hour}:00 ({busiest.volume:,} completed visits).")
        findings.append(f"Longest average wait: {slowest.hour}:00 at {slowest.avg_wait_min} min.")
        findings.append(
            f"Average wait varies by only {spread:.1f} min across hours: no hour-of-day bottleneck is visible."
            if spread < 3 else f"Average wait varies by {spread:.1f} min across hours; review staffing at peak hours."
        )
    overall = get_kpis().avg_wait_minutes
    return WaitInsights(
        summary=(
            f"Average completed-visit wait is {overall} min against a {WAIT_TARGET_MINUTES}-min target. "
            "Wait times are simulated (Synthea records no queue data), so treat patterns as illustrative."
        ),
        findings=findings,
        by_hour=by_hour,
        wait_times_simulated=True,
        target_wait_minutes=WAIT_TARGET_MINUTES,
    )


def get_filters() -> ReceptionFilters:
    def distinct(col: str) -> List[str]:
        df = query_df_strict(f"SELECT DISTINCT {col} AS v FROM gold_appointments WHERE {col} IS NOT NULL ORDER BY v")
        return [str(v) for v in df["v"]]

    return ReceptionFilters(statuses=distinct("status"), departments=distinct("department_name"), visit_types=distinct("visit_type"))


def list_appointments(
    params: PageParams,
    status: Optional[str] = None,
    department: Optional[str] = None,
    visit_type: Optional[str] = None,
) -> Page[AppointmentRow]:
    where, args = ["1=1"], []
    for col, value in (("status", status), ("department_name", department), ("visit_type", visit_type)):
        if value:
            where.append(f"{col} = ?")
            args.append(value)
    df = query_df_strict(
        f"""
        SELECT appointment_id, patient_id, appointment_date, appointment_time,
               doctor_name, department_name, visit_type, status, waiting_time_minutes
        FROM gold_appointments
        WHERE {' AND '.join(where)}
        ORDER BY appointment_date DESC, appointment_time ASC, appointment_id ASC
        LIMIT ? OFFSET ?
        """,
        args + [params.limit + 1, params.offset],
    )
    rows = [
        AppointmentRow(
            appointment_id=r.appointment_id,
            patient_id=r.patient_id,
            appointment_date=r.appointment_date,
            appointment_time=r.appointment_time,
            doctor_name=r.doctor_name,
            department_name=r.department_name,
            visit_type=VISIT_TYPE_LABELS.get(r.visit_type, r.visit_type),
            status=r.status,
            waiting_time_minutes=None if r.waiting_time_minutes != r.waiting_time_minutes else int(r.waiting_time_minutes),
        )
        for r in df.itertuples()
    ]
    return build_page(rows, params)
