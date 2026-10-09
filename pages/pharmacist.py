"""
Pharmacy Intelligence Dashboard for MediNexus AI.
Consumes Gold layer models (gold_pharmacy, gold_prescriptions),
ML medication demand forecasting, prescriptive procurement rules, and the PharmaLab AI Agent.
"""

import streamlit as st
import pandas as pd

from src.analytics.metrics import compute_pharmacy_kpis
from src.analytics.descriptive import get_pharmacy_stock_chart
from src.ml.predict import predict_drug_demand
from src.prescriptive.pharmacy_rules import get_pharmacy_prescriptive_actions
from src.agents.pharmalab_agent import PharmaLabAgent
from src.utils.chat_ui import render_ai_chatbot
from src.utils.database import query_df
from src.utils.helpers import format_number, format_currency, PALETTE
from src.security.audit import log_audit_event


def render_pharmacist_page():
    """Render Clinical Pharmacist intelligence dashboard."""
    user = st.session_state.get("user", {})
    username = user.get("username", "pharmacist_patel")

    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div>
                <h2 style="color: #0F172A; font-weight: 800; margin: 0;">Pharmacy & Supply Chain Intelligence Console</h2>
                <p style="color: #64748B; margin: 0; font-size: 0.92rem;">
                    Formulary Inventory Monitoring, 30-Day Demand Forecasting, Stockout Prevention, and PharmaLab Copilot.
                </p>
            </div>
            <span style="background: #0D9488; color: white; padding: 5px 12px; border-radius: 6px; font-weight: 600; font-size: 0.82rem;">
                GOLD PHARMACY MART
            </span>
        </div>
    """, unsafe_allow_html=True)

    df_check = query_df("SELECT COUNT(*) as cnt FROM gold_pharmacy")
    if df_check.empty or int(df_check.iloc[0]["cnt"]) == 0:
        st.info("Lakehouse gold models are awaiting ingestion. Please run the Medallion Pipeline in Data Engineering.")
        return

    # 1. Pharmacy KPIs
    kpis = compute_pharmacy_kpis()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Formulary Items Tracked", format_number(kpis["total_items"]))
    c2.metric("Critical Stockout Risks", format_number(kpis["high_risk_items"]), delta="Immediate Order", delta_color="inverse")
    c3.metric("Moderate Stockout Risks", format_number(kpis["moderate_risk_items"]))
    c4.metric("Total Dispensed Units", format_number(kpis["total_dispensed_units"]))

    st.markdown("---")

    col_chart, col_alerts = st.columns([3, 2])

    with col_chart:
        st.markdown("### 📊 Inventory Stock vs Reorder Safety Buffer")
        st.plotly_chart(get_pharmacy_stock_chart(), use_container_width=True)

    with col_alerts:
        st.markdown("### ⚠️ Priority Stockout Warnings")
        df_risk = query_df("""
            SELECT medication_id, medication_name, category, stock_quantity,
                   reorder_level, days_of_supply_remaining, stockout_risk
            FROM gold_pharmacy
            WHERE stockout_risk IN ('High Risk', 'Moderate Risk')
            ORDER BY stock_quantity ASC
            LIMIT 6
        """)

        if not df_risk.empty:
            for _, r in df_risk.iterrows():
                badge_color = "#EF4444" if r["stockout_risk"] == "High Risk" else "#F59E0B"
                st.markdown(f"""
                    <div style="border-left: 4px solid {badge_color}; background: #F8FAFC; padding: 10px 14px; border-radius: 4px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between;">
                            <b>{r['medication_name']}</b>
                            <span style="color: {badge_color}; font-weight: 700; font-size: 0.8rem;">{r['stockout_risk'].upper()}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #64748B;">
                            Current Stock: <b>{r['stock_quantity']}</b> | Reorder Buffer: <b>{r['reorder_level']}</b> | Days of Supply: <b>{r['days_of_supply_remaining']}d</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.success("All formulary drugs meet safe inventory buffers.")

    st.markdown("---")

    # 2. Predictive Demand & Prescriptive Procurement Engine
    st.markdown("### 🔮 Predictive Demand Forecasting & Procurement Assistant")
    df_all_meds = query_df("SELECT DISTINCT medication_id, medication_name FROM gold_pharmacy ORDER BY medication_name ASC")

    med_options = {f"{r['medication_name']} ({r['medication_id']})": r["medication_id"] for _, r in df_all_meds.iterrows()}
    selected_label = st.selectbox("Select Formulary Drug for Machine Learning Demand Prediction:", list(med_options.keys()))
    selected_med_id = med_options[selected_label]

    if selected_med_id:
        demand_eval = predict_drug_demand(selected_med_id)
        df_med_row = query_df("SELECT * FROM gold_pharmacy WHERE medication_id = ? LIMIT 1", [selected_med_id]).iloc[0]

        presc_plan = get_pharmacy_prescriptive_actions(
            medication_name=demand_eval["medication_name"],
            current_stock=demand_eval["current_stock"],
            reorder_level=int(df_med_row["reorder_level"]),
            days_of_supply=float(df_med_row["days_of_supply_remaining"]),
            predicted_demand=demand_eval["predicted_30d_demand"],
            unit_cost=float(df_med_row["unit_cost"]),
        )

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Current On-Hand Stock", f"{demand_eval['current_stock']} units")
        p2.metric("Predicted 30-Day Demand", f"{demand_eval['predicted_30d_demand']} units")
        p3.metric("Projected Shortfall", f"{demand_eval['projected_shortfall']} units", delta="Shortage" if demand_eval['projected_shortfall'] > 0 else "Adequate", delta_color="inverse")
        p4.metric("Recommended Purchase Order", f"{presc_plan['recommended_order_quantity']} units", delta=format_currency(presc_plan['estimated_procurement_cost']))

        st.markdown(f"**Buffer Diagnostic:** {presc_plan['buffer_assessment']}")

        st.markdown("##### 🛒 Prescriptive Procurement Directives:")
        for step in presc_plan["action_steps"]:
            st.markdown(f"- ✅ {step}")

        if presc_plan["recommended_order_quantity"] > 0:
            if st.button(f"Generate Electronic PO for {presc_plan['recommended_order_quantity']} Units ({format_currency(presc_plan['estimated_procurement_cost'])})"):
                log_audit_event(
                    username=username,
                    role="Pharmacist",
                    action="PROCUREMENT_ORDER",
                    resource=f"MED_{selected_med_id}",
                    status="SUCCESS",
                    details=f"Generated PO for {presc_plan['recommended_order_quantity']} units of {demand_eval['medication_name']}",
                )
                st.success(f"Electronic Purchase Order generated and dispatched to wholesale vendor distributor!")

    st.markdown("---")

    # 3. Interactive PharmaLab AI Copilot (Modern Chatbot UI)
    st.markdown("---")
    render_ai_chatbot(
        agent_instance=PharmaLabAgent(role="Pharmacist"),
        chat_key="pharma_agent",
        title="PharmaLab AI Copilot",
        subtitle="Gold Formulary Inventory & Cold-Chain Guidelines Grounded",
        suggested_prompts=[
            "Which medicines require immediate replenishment?",
            "What are the temperature standards for refrigerated medications?",
            "Analyze 30-day forecast for critical cardiac medications",
        ],
        username=username,
    )


if __name__ == "__main__":
    if not st.session_state.get("authenticated"):
        from config.settings import DEMO_USERS
        st.session_state["authenticated"] = True
        st.session_state["user"] = DEMO_USERS["pharmacist_patel"]
        st.session_state["username"] = "pharmacist_patel"
        st.session_state["name"] = "Pharmacist"
        st.session_state["role"] = "Pharmacist"
    render_pharmacist_page()

