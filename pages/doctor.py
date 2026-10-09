"""
Doctor & Clinical Intelligence Dashboard for MediNexus AI.
Production-grade Clinical Workstation consuming Gold layer models,
ML predictive risk inference (Readmission & LOS), prescriptive transitional care,
and the MediCare AI Clinical Copilot.
"""

import streamlit as st
import pandas as pd

from src.analytics.metrics import compute_doctor_kpis
from src.analytics.descriptive import get_risk_tier_donut_chart, get_patient_lab_timeline
from src.ml.predict import (
    predict_patient_readmission,
    predict_patient_los,
    predict_patient_covid_outcomes,
    CLINICAL_DISCLAIMER,
)
from src.prescriptive.clinical_rules import get_clinical_prescription_plan
from src.agents.medicare_agent import MediCareAgent
from src.utils.chat_ui import render_ai_chatbot
from src.utils.database import query_df
from src.utils.helpers import get_risk_badge, format_number, PALETTE
from src.security.audit import log_audit_event


def render_doctor_page():
    """Render modern, production-grade Clinical Decision Support Console."""
    user = st.session_state.get("user", {})
    username = user.get("username", "dr_chen")

    # 1. Clean Production Header
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #E2E8F0; margin-bottom: 18px;">
            <div>
                <h2 style="color: #0F172A; font-weight: 700; margin: 0; font-size: 1.55rem; letter-spacing: -0.02em;">Clinical Workstation</h2>
                <span style="color: #64748B; font-size: 0.85rem;">Inpatient Decision Support & Risk Stratification</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #10B981;"></span>
                <span style="color: #475569; font-size: 0.82rem; font-weight: 600;">Lakehouse Connected</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 4-Tier Clinical Analytics Framework Navigator
    st.markdown("""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 16px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="font-weight: 700; color: #0F172A; font-size: 0.85rem;">CLINICAL ANALYTICS SUITE:</div>
            <span style="background: #EFF6FF; color: #1D4ED8; padding: 2px 10px; border-radius: 12px; font-size: 0.76rem; font-weight: 600;">📊 1. Descriptive (Patient 360 EHR)</span>
            <span style="background: #FEF3C7; color: #B45309; padding: 2px 10px; border-radius: 12px; font-size: 0.76rem; font-weight: 600;">🔍 2. Diagnostic (Root Cause Risk Factors)</span>
            <span style="background: #F3E8FF; color: #7E22CE; padding: 2px 10px; border-radius: 12px; font-size: 0.76rem; font-weight: 600;">🔮 3. Predictive (Readmission & LOS AI)</span>
            <span style="background: #ECFDF5; color: #047857; padding: 2px 10px; border-radius: 12px; font-size: 0.76rem; font-weight: 600;">🧭 4. Prescriptive (Care Protocol & Orders)</span>
        </div>
    """, unsafe_allow_html=True)

    # Check if Gold layer is available
    df_check = query_df("SELECT COUNT(*) as cnt FROM gold_patient_360")
    if df_check.empty or int(df_check.iloc[0]["cnt"]) == 0:
        st.info("Clinical data models are initializing. Please run the Medallion Pipeline in Data Engineering.")
        return

    # 2. Executive Clinical KPIs
    kpis = compute_doctor_kpis()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monitored Patients", format_number(kpis["monitored_patients"]))
    c2.metric("High-Risk Priority", format_number(kpis["high_risk_patients"]), delta="Immediate Review", delta_color="inverse")
    c3.metric("Moderate-Risk Cohort", format_number(kpis["moderate_risk_patients"]))
    c4.metric("30-Day Readmission Baseline", f"{kpis['doctor_readmission_rate']}%")

    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    # 3. Two-Column Clinical Layout: Patient 360 Workspace (Left) & Clinical Worklist / Cohort (Right)
    col_main, col_worklist = st.columns([2.6, 1.0], gap="large")

    # --- Right Column: Priority Worklist & Cohort Mix ---
    with col_worklist:
        st.markdown("#### High-Risk Worklist")
        df_high = query_df("""
            SELECT patient_id, name, age, gender, clinical_risk_tier
            FROM gold_patient_360
            WHERE clinical_risk_tier = 'High'
            LIMIT 5
        """)

        if not df_high.empty:
            for _, r in df_high.iterrows():
                is_selected = st.session_state.get("selected_patient_id") == r["patient_id"]
                btn_label = f"🚨 {r['patient_id']} · {r['name']} ({r['age']}y)"
                if st.button(
                    btn_label,
                    key=f"wl_{r['patient_id']}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                ):
                    st.session_state["selected_patient_id"] = r["patient_id"]
                    st.rerun()

        st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
        st.markdown("#### Cohort Risk Distribution")
        fig_donut = get_risk_tier_donut_chart()
        fig_donut.update_layout(
            height=250,
            margin=dict(l=10, r=10, t=30, b=10),
            showlegend=True,
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    # --- Left Column: Patient 360 & Clinical Chart ---
    with col_main:
        # Patient Selector Bar
        df_selector = query_df("""
            SELECT patient_id, name, age, gender, clinical_risk_tier
            FROM gold_patient_360
            ORDER BY patient_id
            LIMIT 100
        """)

        first_pid = str(df_selector.iloc[0]["patient_id"]) if not df_selector.empty else "P_00001"
        current_pid = st.session_state.get("selected_patient_id", first_pid)
        if not df_selector.empty and current_pid not in df_selector["patient_id"].values:
            current_pid = first_pid
            st.session_state["selected_patient_id"] = current_pid

        # Build options dictionary for quick lookup
        options_list = []
        selected_idx = 0
        for i, row in df_selector.iterrows():
            label = f"{row['patient_id']} — {row['name']} ({row['age']}y {row['gender']}, {row['clinical_risk_tier']} Risk)"
            options_list.append(label)
            if row["patient_id"] == current_pid:
                selected_idx = i

        col_sel, col_quick_search = st.columns([3, 1])
        with col_sel:
            selected_option = st.selectbox(
                "Select Patient Record",
                options=options_list,
                index=selected_idx if selected_idx < len(options_list) else 0,
                label_visibility="collapsed",
            )
            if selected_option:
                chosen_pid = selected_option.split(" — ")[0]
                if chosen_pid != current_pid:
                    st.session_state["selected_patient_id"] = chosen_pid
                    st.rerun()

        with col_quick_search:
            manual_search = st.text_input(
                "Search ID / Name",
                placeholder="ID or Name...",
                label_visibility="collapsed",
                key="patient_search_input",
            )
            if manual_search and manual_search.strip() != "":
                df_search = query_df(
                    "SELECT patient_id FROM gold_patient_360 WHERE patient_id ILIKE ? OR name ILIKE ? LIMIT 1",
                    [f"%{manual_search.strip()}%", f"%{manual_search.strip()}%"],
                )
                if not df_search.empty:
                    found_pid = df_search.iloc[0]["patient_id"]
                    if found_pid != current_pid:
                        st.session_state["selected_patient_id"] = found_pid
                        st.rerun()

        # Fetch active patient record
        active_pid = st.session_state.get("selected_patient_id", first_pid)
        df_p = query_df("SELECT * FROM gold_patient_360 WHERE patient_id = ? LIMIT 1", [active_pid])

        if df_p.empty and not df_selector.empty:
            active_pid = str(df_selector.iloc[0]["patient_id"])
            st.session_state["selected_patient_id"] = active_pid
            df_p = query_df("SELECT * FROM gold_patient_360 WHERE patient_id = ? LIMIT 1", [active_pid])

        if df_p.empty:
            st.error(f"Patient {active_pid} record not found.")
            return

        p = df_p.iloc[0].to_dict()

        # Audit log for clinical view
        log_audit_event(
            username=username,
            role="Doctor",
            action="PATIENT_360_VIEW",
            resource=f"PATIENT_{active_pid}",
            status="SUCCESS",
            details=f"Clinical chart access for {active_pid}",
        )

        # Build comorbidities chips
        comorb_raw = str(p.get("comorbidities_list") or "")
        comorb_items = [c.strip() for c in comorb_raw.split(",") if c.strip()][:3]
        comorb_chips = "".join([
            f'<span style="background: #EFF6FF; color: #1D4ED8; padding: 3px 9px; border-radius: 12px; font-size: 0.76rem; font-weight: 500; margin-right: 6px;">{c}</span>'
            for c in comorb_items
        ]) or '<span style="color: #94A3B8; font-size: 0.78rem;">None recorded</span>'

        # Modern Production EHR Patient Banner
        st.markdown(f"""
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 18px 22px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.35rem; font-weight: 700; color: #0F172A;">{p['name']}</span>
                            <span style="background: #F1F5F9; color: #475569; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;">{p['patient_id']}</span>
                            {get_risk_badge(p['clinical_risk_tier'])}
                        </div>
                        <div style="display: flex; gap: 18px; margin-top: 8px; font-size: 0.86rem; color: #475569; flex-wrap: wrap;">
                            <span><b>Demographics:</b> {p['age']} yrs · {p['gender']}</span>
                            <span><b>Blood Group:</b> {p['blood_group']}</span>
                            <span><b>Insurance:</b> {p['insurance_provider']}</span>
                            <span><b>Inpatient Encounters:</b> {p['total_admissions']} (ALOS: {p['avg_los']}d)</span>
                        </div>
                    </div>
                </div>
                <div style="margin-top: 12px; padding-top: 10px; border-top: 1px solid #F1F5F9; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; font-weight: 600; color: #64748B;">Chronic Conditions:</span>
                    <div>{comorb_chips}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # 4. Clinical Workspace Tabs
        tab_risk, tab_biomarkers, tab_meds, tab_encounters, tab_copilot = st.tabs([
            "🎯 Risk & Care Plan",
            "🔬 Biomarkers & Labs",
            "💊 Active Medications",
            "🏥 Encounter History",
            "💬 MediCare AI Copilot",
        ])

        # --- TAB 1: Predictive Risk & Care Plan ---
        with tab_risk:
            st.markdown("#### 🦠 Predictive Analytics: COVID-19 Severe Outcome Risk")
            covid_eval = predict_patient_covid_outcomes(active_pid)
            if covid_eval.get("status") == "SUCCESS":
                st.caption(
                    f"Scored as of the {covid_eval['scored_as_of']} using only history recorded before that date. "
                    "Risk bands are relative to the COVID-19 cohort (top 10% = HIGH)."
                )
                band_colors = {"HIGH": "#EF4444", "MODERATE": "#F59E0B", "LOW": "#10B981"}
                covid_cols = st.columns(len(covid_eval["outcomes"]))
                for col, (outcome, res) in zip(covid_cols, covid_eval["outcomes"].items()):
                    observed = res["observed"]
                    observed_txt = "" if observed is None else f"<br>Observed: <b>{'Yes' if observed == 1 else 'No'}</b>"
                    with col:
                        st.markdown(f"""
                            <div style="border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; background: #FFFFFF;">
                                <div style="font-weight: 600; color: #64748B; font-size: 0.74rem; text-transform: uppercase;">{res['label']}</div>
                                <div style="font-size: 1.4rem; font-weight: 800; color: {band_colors.get(res['risk_level'], '#0284C7')}; margin: 6px 0 2px 0;">{res['probability']}%</div>
                                <div style="font-size: 0.76rem; color: #64748B;">{res['risk_level']} · cohort rate {res['cohort_rate_pct']}%{observed_txt}</div>
                            </div>
                        """, unsafe_allow_html=True)
                st.caption("Pre-existing risk drivers: " + ", ".join(covid_eval.get("risk_drivers", [])))
            else:
                st.info(covid_eval.get("message", "COVID-19 outcome model unavailable."))

            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 🔮 Predictive Analytics: Unplanned 30-Day Readmission Risk & Expected LOS")
            readm_eval = predict_patient_readmission(active_pid)
            los_eval = predict_patient_los(active_pid)

            col_r1, col_r2 = st.columns(2)

            risk_level = readm_eval.get("risk_level", "LOW")
            prob = readm_eval.get("probability", 0.0)

            # Risk color coding
            if risk_level == "HIGH":
                color_accent = "#EF4444"
                bar_bg = "#EF4444"
            elif risk_level == "MODERATE":
                color_accent = "#F59E0B"
                bar_bg = "#F59E0B"
            else:
                color_accent = "#10B981"
                bar_bg = "#10B981"

            with col_r1:
                st.markdown(f"""
                    <div style="border: 1px solid #E2E8F0; border-radius: 8px; padding: 18px; background: #FFFFFF; height: 100%;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #64748B; font-size: 0.82rem; text-transform: uppercase;">Unplanned 30-Day Readmission Risk</span>
                            <span style="font-size: 0.8rem; color: #64748B;">Model v{readm_eval.get('model_version', '1.0')}</span>
                        </div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: {color_accent}; margin: 8px 0 2px 0;">
                            {risk_level} RISK
                        </div>
                        <div style="font-size: 1rem; color: #1E293B; font-weight: 600; margin-bottom: 6px;">
                            {prob}% Probability
                        </div>
                        <div style="background: #F1F5F9; border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 10px;">
                            <div style="background: {bar_bg}; height: 100%; width: {min(100, prob)}%; border-radius: 6px;"></div>
                        </div>
                        <span style="font-size: 0.78rem; color: #64748B;">{readm_eval.get('confidence', 'Standard')} · cohort base rate <b>{readm_eval.get('cohort_base_rate_pct', 'n/a')}%</b></span>
                    </div>
                """, unsafe_allow_html=True)

            with col_r2:
                pred_los = los_eval.get("predicted_los_days", "N/A")
                ci = los_eval.get("confidence_interval", "N/A")
                st.markdown(f"""
                    <div style="border: 1px solid #E2E8F0; border-radius: 8px; padding: 18px; background: #FFFFFF; height: 100%;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #64748B; font-size: 0.82rem; text-transform: uppercase;">Expected Length of Stay</span>
                            <span style="font-size: 0.8rem; color: #64748B;">GradientBoosting</span>
                        </div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: #0284C7; margin: 8px 0 2px 0;">
                            {pred_los} Days
                        </div>
                        <div style="font-size: 0.92rem; color: #334155; margin-bottom: 8px; margin-top: 6px;">
                            Expected Interval: <b>{ci}</b>
                        </div>
                        <div style="margin-top: 14px;">
                            <span style="font-size: 0.78rem; color: #64748B;">Historical ALOS Benchmark: <b>{p.get('avg_los', 4.0)}d</b></span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            # Key Contributing Risk Factors
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 🔍 Diagnostic Analytics: Key Risk Drivers & Clinical Attributions")
            factors = readm_eval.get("contributing_factors", [])
            if factors:
                factor_cols = st.columns(min(len(factors), 3))
                for idx, f in enumerate(factors[:3]):
                    with factor_cols[idx]:
                        st.markdown(f"""
                            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px 14px; font-size: 0.84rem; color: #334155;">
                                ⚠️ {f}
                            </div>
                        """, unsafe_allow_html=True)

            # Prescriptive Transitional Care Protocol
            st.markdown("<div style='margin-top: 22px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 🧭 Prescriptive Analytics: Transitional Care Protocol & Discharge Checklist")
            care_plan = get_clinical_prescription_plan(readm_eval, p)

            st.markdown(f"""
                <div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px;">
                    <span style="font-weight: 700; color: #15803D; font-size: 0.85rem;">RECOMMENDED PROTOCOL:</span>
                    <span style="color: #166534; font-size: 0.88rem; margin-left: 8px;">{care_plan['primary_recommendation']}</span>
                </div>
            """, unsafe_allow_html=True)

            st.markdown("**Discharge Checklist:**")
            for item in care_plan["actionable_checklist"]:
                st.checkbox(item, value=False, key=f"chk_{active_pid}_{item[:20]}")

            with st.expander("Clinical Rationale & Evidence Base"):
                for rat in care_plan["clinical_rationale"]:
                    st.markdown(f"- {rat}")
                st.caption("Guideline Reference: CPG-CLIN-001 (Transitional Care Management)")

            st.markdown(f"""
                <p style="font-size: 0.74rem; color: #94A3B8; margin-top: 20px; border-top: 1px solid #F1F5F9; padding-top: 8px;">
                    ⚖️ {CLINICAL_DISCLAIMER}
                </p>
            """, unsafe_allow_html=True)

        # --- TAB 2: Biomarkers & Laboratory ---
        with tab_biomarkers:
            st.markdown("##### Longitudinal Biomarker Trajectory")
            fig_lab = get_patient_lab_timeline(active_pid)
            fig_lab.update_layout(height=320, margin=dict(l=30, r=20, t=30, b=30))
            st.plotly_chart(fig_lab, use_container_width=True)

            st.markdown("##### Recent Laboratory Results")
            df_recent_labs = query_df(
                """
                SELECT test_name as "Test Name",
                       test_value as "Value",
                       unit as "Unit",
                       reference_range as "Reference Range",
                       abnormal_flag as "Status",
                       test_date as "Date"
                FROM gold_laboratory
                WHERE patient_id = ?
                ORDER BY test_date DESC
                LIMIT 10
                """,
                [active_pid],
            )
            if not df_recent_labs.empty:
                st.dataframe(df_recent_labs, use_container_width=True, hide_index=True)
            else:
                st.info("No laboratory records found for this patient.")

        # --- TAB 3: Active Medications ---
        with tab_meds:
            st.markdown("##### Active Formulary Prescriptions")
            df_meds = query_df(
                """
                SELECT medication_name as "Medication",
                       dosage as "Dosage",
                       frequency as "Frequency",
                       duration_days as "Duration (Days)",
                       quantity as "Quantity",
                       status as "Status",
                       prescription_date as "Prescribed Date"
                FROM gold_prescriptions
                WHERE patient_id = ?
                ORDER BY prescription_date DESC
                """,
                [active_pid],
            )
            if not df_meds.empty:
                st.dataframe(df_meds, use_container_width=True, hide_index=True)
            else:
                st.info("No active prescriptions recorded for this patient.")

        # --- TAB 4: Encounters & Diagnoses ---
        with tab_encounters:
            st.markdown("##### Inpatient Admissions & Clinical Diagnoses")
            df_dx = query_df(
                """
                SELECT icd10_code as "ICD-10",
                       diagnosis_description as "Diagnosis",
                       diagnosis_type as "Encounter Type",
                       severity as "Severity",
                       admission_date as "Admission Date",
                       discharge_date as "Discharge Date",
                       length_of_stay as "LOS (Days)",
                       department_name as "Department",
                       attending_doctor as "Attending Doctor"
                FROM gold_clinical
                WHERE patient_id = ?
                ORDER BY admission_date DESC
                """,
                [active_pid],
            )
            if not df_dx.empty:
                st.dataframe(df_dx, use_container_width=True, hide_index=True)
            else:
                st.info("No historical inpatient encounters found for this patient.")

        # --- TAB 5: MediCare AI Copilot ---
        with tab_copilot:
            render_ai_chatbot(
                agent_instance=MediCareAgent(),
                chat_key="doctor_medicare",
                title="MediCare AI Clinical Copilot",
                subtitle="Patient 360 & Clinical Practice Guidelines Grounded",
                suggested_prompts=[
                    f"Summarize clinical chart for {active_pid}",
                    "What does Guideline CPG-CLIN-001 recommend for discharge?",
                    "What are the drug interaction considerations for this patient?",
                ],
                username=username,
            )


if __name__ == "__main__":
    if not st.session_state.get("authenticated"):
        from config.settings import DEMO_USERS
        st.session_state["authenticated"] = True
        st.session_state["user"] = DEMO_USERS["dr_chen"]
        st.session_state["username"] = "dr_chen"
        st.session_state["name"] = "Doctor"
        st.session_state["role"] = "Doctor"
    render_doctor_page()
