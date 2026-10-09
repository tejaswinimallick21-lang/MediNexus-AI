"""
Laboratory Operations Dashboard for MediNexus AI.
Consumes Gold layer models (gold_laboratory, gold_admissions),
workload forecasts, critical value alert escalations, and the PharmaLab AI Agent.
"""

import streamlit as st
import pandas as pd

from src.analytics.metrics import compute_lab_kpis
from src.analytics.descriptive import get_lab_category_workload_chart
from src.prescriptive.laboratory_rules import get_laboratory_prescriptive_plan
from src.agents.pharmalab_agent import PharmaLabAgent
from src.utils.chat_ui import render_ai_chatbot
from src.utils.database import query_df
from src.utils.helpers import format_number, PALETTE
from src.security.audit import log_audit_event


def render_laboratory_page():
    """Render Laboratory Operations Specialist dashboard."""
    user = st.session_state.get("user", {})
    username = user.get("username", "lab_tech_kim")

    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div>
                <h2 style="color: #0F172A; font-weight: 800; margin: 0;">Diagnostic Laboratory Operations Console</h2>
                <p style="color: #64748B; margin: 0; font-size: 0.92rem;">
                    Specimen Investigation Throughput, Critical Biomarker Alarms, Capacity Planning, and PharmaLab Copilot.
                </p>
            </div>
            <span style="background: #6366F1; color: white; padding: 5px 12px; border-radius: 6px; font-weight: 600; font-size: 0.82rem;">
                GOLD LABORATORY MART
            </span>
        </div>
    """, unsafe_allow_html=True)

    df_check = query_df("SELECT COUNT(*) as cnt FROM gold_laboratory")
    if df_check.empty or int(df_check.iloc[0]["cnt"]) == 0:
        st.info("Lakehouse gold models are awaiting ingestion. Please run the Medallion Pipeline in Data Engineering.")
        return

    # 1. Laboratory KPIs
    kpis = compute_lab_kpis()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Completed Investigations", format_number(kpis["total_tests"]))
    c2.metric("Abnormal Findings Volume", format_number(kpis["abnormal_tests"]), delta=f"{kpis['abnormal_pct']}% of tests")
    c3.metric("Critical Value Alarms", format_number(kpis["critical_tests"]), delta=f"{kpis['critical_pct']}% Critical", delta_color="inverse")
    c4.metric("STAT TAT Benchmark", "98.2%", delta="Within 45m Target")

    st.markdown("---")

    col_chart, col_critical = st.columns([3, 2])

    with col_chart:
        st.markdown("### 🔬 Test Volume by Discipline & Severity")
        st.plotly_chart(get_lab_category_workload_chart(), use_container_width=True)

    with col_critical:
        st.markdown("### 🚨 Critical Value Escalation Feed")
        df_crit = query_df("""
            SELECT lab_id, patient_id, test_name, test_value, unit, test_date
            FROM gold_laboratory
            WHERE is_critical = 1
            ORDER BY test_date DESC
            LIMIT 5
        """)

        if not df_crit.empty:
            for _, r in df_crit.iterrows():
                st.markdown(f"""
                    <div style="border-left: 4px solid #EF4444; background: #FEF2F2; padding: 10px 14px; border-radius: 4px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between;">
                            <b>{r['test_name']}</b>
                            <span style="color: #DC2626; font-weight: 700; font-size: 0.8rem;">CRITICAL ALARM</span>
                        </div>
                        <div style="font-size: 0.9rem; color: #991B1B;">
                            Value: <b>{r['test_value']} {r['unit']}</b> | Patient ID: <b>{r['patient_id']}</b>
                        </div>
                        <div style="font-size: 0.75rem; color: #7F1D1D; margin-top: 4px;">
                            Required Action: 15-min direct verbal physician notification (POL-LAB-001)
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No active critical value alarms recorded.")

    st.markdown("---")

    # 2. Workload Capacity & Prescriptive Staffing Plan
    st.markdown("### ⚙️ Workload Capacity & Prescriptive Staffing Allocator")
    categories = query_df("SELECT DISTINCT test_category FROM gold_laboratory ORDER BY test_category ASC")
    cat_list = categories["test_category"].tolist() if not categories.empty else ["Biochemistry"]

    selected_category = st.selectbox("Select Laboratory Specialty for Capacity Analysis:", cat_list)

    if selected_category:
        df_cat_stat = query_df("""
            SELECT
                COUNT(*) as total_tests,
                SUM(is_critical) as crit_cnt,
                ROUND(AVG(is_critical) * 100, 1) as crit_rate
            FROM gold_laboratory
            WHERE test_category = ?
        """, [selected_category]).iloc[0]

        daily_est = int(df_cat_stat["total_tests"] // 120)
        lab_plan = get_laboratory_prescriptive_plan(
            category=selected_category,
            projected_daily_tests=daily_est,
            critical_rate_pct=float(df_cat_stat["crit_rate"]),
            current_capacity=140,
        )

        p1, p2, p3 = st.columns(3)
        p1.metric("Projected Daily Test Volume", f"{daily_est} tests/day")
        p2.metric("Analyzer Bench Utilization", f"{lab_plan['utilization_percentage']}%")
        p3.metric("Capacity Status", lab_plan["operational_status"])

        st.markdown(f"**Throughput Evaluation:** {lab_plan['analyzer_capacity_assessment']}")

        st.markdown("##### 📋 Recommended Staffing & Maintenance Actions:")
        for action in lab_plan["recommended_staffing_actions"]:
            st.markdown(f"- ✅ {action}")

    st.markdown("---")

    # 3. Interactive PharmaLab AI Copilot (Modern Chatbot UI)
    st.markdown("---")
    render_ai_chatbot(
        agent_instance=PharmaLabAgent(role="Laboratory Technician"),
        chat_key="lab_agent",
        title="PharmaLab AI Copilot (Laboratory)",
        subtitle="Gold Laboratory Mart & Panic Value Protocols Grounded",
        suggested_prompts=[
            "Review workload projections for automated chemistry",
            "What is the critical value notification procedure?",
            "Identify analyzers exceeding turnaround time benchmarks",
        ],
        username=username,
    )


if __name__ == "__main__":
    if not st.session_state.get("authenticated"):
        from config.settings import DEMO_USERS
        st.session_state["authenticated"] = True
        st.session_state["user"] = DEMO_USERS["lab_tech_kim"]
        st.session_state["username"] = "lab_tech_kim"
        st.session_state["name"] = "Laboratory Specialist"
        st.session_state["role"] = "Laboratory"
    render_laboratory_page()

