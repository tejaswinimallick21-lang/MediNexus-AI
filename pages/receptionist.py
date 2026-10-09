"""
Receptionist & Outpatient Flow Dashboard for MediNexus AI.
Consumes Gold layer models (gold_appointments).
Strictly enforces privacy: NO clinical diagnoses, ICD-10 codes, or laboratory biomarker values exposed.
"""

import streamlit as st
import pandas as pd

from src.analytics.metrics import compute_reception_kpis
from src.analytics.descriptive import get_appointment_status_chart
from src.analytics.diagnostic import diagnose_waiting_times
from src.utils.database import query_df, execute_query
from src.utils.helpers import format_number, PALETTE
from src.security.audit import log_audit_event


def render_receptionist_page():
    """Render Outpatient Reception & Patient Flow dashboard."""
    user = st.session_state.get("user", {})
    username = user.get("username", "receptionist_davis")

    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div>
                <h2 style="color: #0F172A; font-weight: 800; margin: 0;">Outpatient Reception & Care Flow Console</h2>
                <p style="color: #64748B; margin: 0; font-size: 0.95rem;">
                    Appointment Bookings, Patient Check-In Queues, Waiting Time Benchmarks, and Care Access Flow.
                </p>
            </div>
            <span style="background: #0284C7; color: white; padding: 6px 14px; border-radius: 6px; font-weight: 600; font-size: 0.85rem;">
                GOLD APPOINTMENTS ONLY (RESTRICTED RBAC)
            </span>
        </div>
    """, unsafe_allow_html=True)

    # Strict Privacy Alert
    st.markdown("""
        <div style="background: #F1F5F9; border-left: 4px solid #64748B; padding: 10px 14px; border-radius: 4px; margin-bottom: 20px; font-size: 0.85rem; color: #334155;">
            🔒 <b>Privacy Governance Notice (POL-HOSP-003):</b> In compliance with Role-Based Access Controls and patient confidentiality, clinical diagnoses, ICD-10 codes, and laboratory investigation findings are strictly masked for front-desk administrative personnel.
        </div>
    """, unsafe_allow_html=True)

    df_check = query_df("SELECT COUNT(*) as cnt FROM gold_appointments")
    if df_check.empty or int(df_check.iloc[0]["cnt"]) == 0:
        st.info("Lakehouse gold models are awaiting ingestion. Please run the Medallion Pipeline in Data Engineering.")
        return

    # 1. Front-Desk KPIs
    kpis = compute_reception_kpis()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scheduled Clinic Visits", format_number(kpis["total_appointments"]))
    c2.metric("Completed Consultations", format_number(kpis["completed"]))
    c3.metric("No-Show Rate", f"{kpis['no_show_rate_pct']}%", delta="Follow-up Required", delta_color="inverse")
    c4.metric("Average Waiting Duration", f"{kpis['avg_wait_minutes']} mins", delta="Target <= 20 mins")

    st.markdown("---")

    col_chart, col_delay = st.columns([1, 1])

    with col_chart:
        st.markdown("### 📋 Outpatient Attendance Distribution")
        st.plotly_chart(get_appointment_status_chart(), use_container_width=True)

    with col_delay:
        st.markdown("### ⏱️ Diagnostic Waiting Time Insights")
        diag = diagnose_waiting_times()
        st.markdown(f"**Diagnostic Finding:** {diag['summary']}")
        st.markdown("##### Key Observed Delay Drivers:")
        for factor in diag["associated_factors"]:
            st.markdown(f"- ⚠️ {factor}")

        st.markdown("""
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; padding: 12px; margin-top: 15px;">
                <b>Front-Desk Action Directive (POL-HOSP-002):</b> When waiting room duration exceeds 25 minutes, receptionists must verbally notify the patient and offer water/seating comfort reassurances.
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 2. Live Patient Appointment & Queue Viewer
    st.markdown("### 🗂️ Clinic Appointment Queue & Check-In Log")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox("Filter by Status", ["All Statuses", "Scheduled", "Completed", "Cancelled", "No-Show"])
    with col_f2:
        dept_df = query_df("SELECT DISTINCT department_name FROM gold_appointments WHERE department_name IS NOT NULL ORDER BY department_name ASC")
        depts = ["All Departments"] + dept_df["department_name"].tolist() if not dept_df.empty else ["All Departments"]
        selected_dept = st.selectbox("Filter by Department", depts)

    query_sql = """
        SELECT appointment_id, patient_id, patient_name, contact,
               appointment_date, appointment_time, doctor_name, department_name,
               status, waiting_time_minutes, reason_for_visit
        FROM gold_appointments
        WHERE 1=1
    """
    params = []
    if status_filter != "All Statuses":
        query_sql += " AND status = ?"
        params.append(status_filter)
    if selected_dept != "All Departments":
        query_sql += " AND department_name = ?"
        params.append(selected_dept)

    query_sql += " ORDER BY appointment_date DESC, appointment_time ASC LIMIT 25"

    df_queue = query_df(query_sql, params)

    if not df_queue.empty:
        st.dataframe(
            df_queue[[
                "appointment_id", "patient_name", "contact", "appointment_date",
                "appointment_time", "doctor_name", "department_name", "status",
                "waiting_time_minutes", "reason_for_visit"
            ]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No appointment records matched the selected filter criteria.")


if __name__ == "__main__":
    if not st.session_state.get("authenticated"):
        from config.settings import DEMO_USERS
        st.session_state["authenticated"] = True
        st.session_state["user"] = DEMO_USERS["receptionist_davis"]
        st.session_state["username"] = "receptionist_davis"
        st.session_state["name"] = "Receptionist"
        st.session_state["role"] = "Receptionist"
    render_receptionist_page()

