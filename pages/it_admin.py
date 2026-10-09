"""
IT & Security Administrator Console for MediNexus AI.
Monitors system health, DuckDB table schemas, pipeline ingestion logs,
machine learning model health, and the immutable enterprise audit trail.
"""

import streamlit as st
import os
from pathlib import Path
import pandas as pd

from config.constants import DATABASE_PATH, LOGS_DIR
from src.security.audit import get_audit_trail
from src.ml.model_registry import get_model_registry_summary
from src.utils.database import query_df
from src.utils.helpers import format_number, PALETTE


def render_it_admin_page():
    """Render IT Infrastructure and Security Monitoring dashboard."""
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div>
                <h2 style="color: #0F172A; font-weight: 800; margin: 0;">Enterprise IT & Security Audit Console</h2>
                <p style="color: #64748B; margin: 0; font-size: 0.95rem;">
                    Infrastructure Health, Lakehouse Database Status, Medallion Pipeline Ingestion Logs, and Security Audit Stream.
                </p>
            </div>
            <span style="background: #1E293B; color: #38BDF8; padding: 6px 14px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; border: 1px solid #38BDF8;">
                SECURITY AUDIT ACTIVE
            </span>
        </div>
    """, unsafe_allow_html=True)

    # 1. System Health KPIs
    db_size_mb = round(os.path.getsize(DATABASE_PATH) / (1024 * 1024), 2) if DATABASE_PATH.exists() else 0.0
    table_cnt = query_df("SELECT COUNT(*) as cnt FROM information_schema.tables WHERE table_schema = 'main'")
    total_tables = int(table_cnt.iloc[0]["cnt"]) if not table_cnt.empty else 0
    audit_cnt = query_df("SELECT COUNT(*) as cnt FROM audit_logs")
    total_audits = int(audit_cnt.iloc[0]["cnt"]) if not audit_cnt.empty else 0
    model_cnt = query_df("SELECT COUNT(*) as cnt FROM model_registry WHERE status = 'ACTIVE'")
    active_models = int(model_cnt.iloc[0]["cnt"]) if not model_cnt.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("DuckDB Storage Footprint", f"{db_size_mb} MB")
    c2.metric("Managed Database Tables", f"{total_tables} Tables")
    c3.metric("Registered ML Models", f"{active_models} Active")
    c4.metric("Logged Security Audit Events", format_number(total_audits))

    st.markdown("---")

    # 2. Main Tabs
    tab_audit, tab_tables, tab_pipelines, tab_ingestion = st.tabs([
        "🛡️ Enterprise Audit Stream",
        "🗄️ Database Table Explorer",
        "⚙️ Pipeline Runs & Errors",
        "📥 Bronze Ingestion Logs",
    ])

    with tab_audit:
        st.markdown("#### Live Security & Access Audit Trail")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            role_choice = st.selectbox(
                "Filter by Role",
                ["All Roles", "Data Engineer", "Doctor", "Pharmacist", "Laboratory Technician", "Receptionist", "Hospital Administrator", "IT Administrator"]
            )
        with col_f2:
            action_choice = st.selectbox(
                "Filter by Action",
                ["All Actions", "LOGIN", "PATIENT_SEARCH", "PATIENT_360_VIEW", "PIPELINE_RUN", "MODEL_TRAIN", "AGENT_QUERY", "PROCUREMENT_ORDER"]
            )

        df_audit = get_audit_trail(limit=100, role_filter=role_choice, action_filter=action_choice)

        if not df_audit.empty:
            st.dataframe(
                df_audit[["timestamp", "username", "role", "action", "resource", "status", "details"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No audit events recorded under this filter.")

    with tab_tables:
        st.markdown("#### DuckDB Lakehouse Tables & Views")
        df_all_tables = query_df("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name ASC
        """)

        if not df_all_tables.empty:
            selected_tbl = st.selectbox("Select Table to Inspect:", df_all_tables["table_name"].tolist())
            if selected_tbl:
                row_cnt = query_df(f"SELECT COUNT(*) as cnt FROM {selected_tbl}").iloc[0]["cnt"]
                st.markdown(f"**Table:** `{selected_tbl}` | **Total Row Count:** `{row_cnt:,}`")

                st.markdown("##### Preview First 5 Records:")
                df_preview = query_df(f"SELECT * FROM {selected_tbl} LIMIT 5")
                st.dataframe(df_preview, use_container_width=True, hide_index=True)
        else:
            st.info("No tables currently found in DuckDB.")

    with tab_pipelines:
        st.markdown("#### Medallion Pipeline Execution History")
        df_pipes = query_df("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 15")
        if not df_pipes.empty:
            st.dataframe(df_pipes, use_container_width=True, hide_index=True)
        else:
            st.info("No pipeline executions logged.")

    with tab_ingestion:
        st.markdown("#### Raw Ingestion Run Records (Bronze Layer)")
        df_ingest = query_df("SELECT * FROM ingestion_runs ORDER BY ingestion_timestamp DESC LIMIT 20")
        if not df_ingest.empty:
            st.dataframe(df_ingest, use_container_width=True, hide_index=True)
        else:
            st.info("No Bronze ingestion runs logged.")


if __name__ == "__main__":
    if not st.session_state.get("authenticated"):
        from config.settings import DEMO_USERS
        st.session_state["authenticated"] = True
        st.session_state["user"] = DEMO_USERS["it_admin_torvalds"]
        st.session_state["username"] = "it_admin_torvalds"
        st.session_state["name"] = "IT Administrator"
        st.session_state["role"] = "IT Administrator"
    render_it_admin_page()

