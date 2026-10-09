"""
Descriptive Analytics and Plotly Visualizations for MediNexus AI.
"""

from typing import Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.utils.database import query_df
from src.utils.helpers import apply_healthcare_chart_theme, PALETTE


def get_admissions_trend_chart() -> go.Figure:
    """Monthly admissions trend chart."""
    df = query_df("""
        SELECT
            SUBSTR(admission_date, 1, 7) as month_year,
            COUNT(*) as admissions_count,
            SUM(readmitted_30d) as readmission_count
        FROM gold_admissions
        GROUP BY month_year
        ORDER BY month_year ASC
    """)
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["month_year"],
        y=df["admissions_count"],
        name="Total Inpatient Admissions",
        marker_color=PALETTE["secondary"],
    ))
    fig.add_trace(go.Scatter(
        x=df["month_year"],
        y=df["readmission_count"],
        name="30-Day Readmissions",
        mode="lines+markers",
        line=dict(color=PALETTE["danger"], width=3),
    ))
    return apply_healthcare_chart_theme(fig, "Inpatient Admission Volume & 30-Day Readmission Trend")


def get_department_revenue_chart() -> go.Figure:
    """Department revenue breakdown bar chart."""
    df = query_df("""
        SELECT department_name, SUM(total_amount) as revenue
        FROM gold_billing
        GROUP BY department_name
        ORDER BY revenue DESC
    """)
    if df.empty:
        return go.Figure()

    fig = px.bar(
        df,
        x="department_name",
        y="revenue",
        title="Departmental Revenue Distribution ($)",
        labels={"department_name": "Clinical Specialty", "revenue": "Total Billed ($)"},
        color="revenue",
        color_continuous_scale="Teal",
    )
    return apply_healthcare_chart_theme(fig, "Departmental Billed Revenue")


def get_risk_tier_donut_chart() -> go.Figure:
    """Clinical risk classification breakdown."""
    df = query_df("""
        SELECT clinical_risk_tier, COUNT(*) as patient_count
        FROM gold_patient_360
        GROUP BY clinical_risk_tier
    """)
    if df.empty:
        return go.Figure()

    colors = {
        "High": PALETTE["danger"],
        "Moderate": PALETTE["warning"],
        "Low": PALETTE["success"],
    }
    fig = px.pie(
        df,
        names="clinical_risk_tier",
        values="patient_count",
        hole=0.45,
        color="clinical_risk_tier",
        color_discrete_map=colors,
    )
    return apply_healthcare_chart_theme(fig, "Patient Cohort Risk Classification")


def get_patient_lab_timeline(patient_id: str) -> go.Figure:
    """Individual patient longitudinal lab biomarker trajectory."""
    df = query_df("""
        SELECT test_name, test_value, test_date, abnormal_flag
        FROM gold_laboratory
        WHERE patient_id = ?
        ORDER BY test_date ASC
    """, [patient_id])
    if df.empty:
        return go.Figure()

    fig = px.scatter(
        df,
        x="test_date",
        y="test_value",
        color="test_name",
        symbol="abnormal_flag",
        labels={"test_date": "Specimen Date", "test_value": "Biomarker Value"},
    )
    return apply_healthcare_chart_theme(fig, f"Biomarker Trajectory - Patient {patient_id}")


def get_pharmacy_stock_chart() -> go.Figure:
    """Pharmacy inventory vs reorder threshold."""
    df = query_df("""
        SELECT medication_name, stock_quantity, reorder_level, stockout_risk
        FROM gold_pharmacy
        ORDER BY stock_quantity ASC
        LIMIT 12
    """)
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["medication_name"],
        y=df["stock_quantity"],
        name="Current Stock (Units)",
        marker_color=PALETTE["primary"],
    ))
    fig.add_trace(go.Scatter(
        x=df["medication_name"],
        y=df["reorder_level"],
        name="Reorder Safety Buffer",
        mode="lines+markers",
        line=dict(color=PALETTE["danger"], width=2, dash="dash"),
    ))
    return apply_healthcare_chart_theme(fig, "Pharmacy Inventory Stock vs Reorder Level")


def get_lab_category_workload_chart() -> go.Figure:
    """Laboratory test volume by category with abnormal breakdown."""
    df = query_df("""
        SELECT
            test_category,
            COUNT(*) as total_tests,
            SUM(is_abnormal) as abnormal_tests,
            SUM(is_critical) as critical_tests
        FROM gold_laboratory
        GROUP BY test_category
        ORDER BY total_tests DESC
    """)
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["test_category"],
        y=df["total_tests"],
        name="Total Tests Conducted",
        marker_color=PALETTE["secondary"],
    ))
    fig.add_trace(go.Bar(
        x=df["test_category"],
        y=df["abnormal_tests"],
        name="Abnormal Findings",
        marker_color=PALETTE["warning"],
    ))
    fig.add_trace(go.Bar(
        x=df["test_category"],
        y=df["critical_tests"],
        name="Life-Critical Alerts",
        marker_color=PALETTE["danger"],
    ))
    fig.update_layout(barmode="group")
    return apply_healthcare_chart_theme(fig, "Laboratory Investigation Volume & Alert Severity")


def get_appointment_status_chart() -> go.Figure:
    """Appointment attendance and waiting time distribution."""
    df = query_df("""
        SELECT status, COUNT(*) as count
        FROM gold_appointments
        GROUP BY status
    """)
    if df.empty:
        return go.Figure()

    fig = px.pie(
        df,
        names="status",
        values="count",
        hole=0.4,
        color_discrete_sequence=[PALETTE["primary"], PALETTE["secondary"], PALETTE["danger"], PALETTE["warning"]],
    )
    return apply_healthcare_chart_theme(fig, "Outpatient Appointment Attendance Distribution")
