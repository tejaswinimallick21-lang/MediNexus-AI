"""
PharmaLab Agent for MediNexus AI.
Combined intelligent copilot for Clinical Pharmacists and Laboratory Specialists.
Supports inventory intelligence, medication demand forecasting, lab workload projections, and critical test alerts.
"""

from typing import Dict, Any, List
import pandas as pd

from src.agents.base_agent import BaseHealthcareAgent
from src.utils.database import query_df
from src.ml.predict import predict_drug_demand
from src.prescriptive.pharmacy_rules import get_pharmacy_prescriptive_actions
from src.prescriptive.laboratory_rules import get_laboratory_prescriptive_plan
from src.rag.knowledge_base import generate_grounded_answer
from src.security.audit import log_audit_event


class PharmaLabAgent(BaseHealthcareAgent):
    """
    Intelligent Copilot for Pharmacy and Laboratory Operations.
    """

    def __init__(self, role: str = "Pharmacist"):
        super().__init__(
            agent_name="PharmaLab Agent",
            role=role,
            system_prompt=(
                f"You are PharmaLab Agent, an AI decision-support specialist serving {role} personnel. "
                "You assist with medication supply chain risk, prescription utilization patterns, "
                "laboratory investigation volume, critical test alarms, and equipment throughput. "
                "Always cite verified Gold analytical data and institutional guidelines."
            ),
        )

    def analyze_pharmacy_risks(self) -> Dict[str, Any]:
        """Analyze pharmacy inventory, stockouts, and demand forecasting."""
        df_low_stock = query_df("""
            SELECT medication_id, medication_name, category, stock_quantity,
                   reorder_level, days_of_supply_remaining, stockout_risk,
                   suggested_reorder_qty, unit_cost
            FROM gold_pharmacy
            WHERE stockout_risk IN ('High Risk', 'Moderate Risk')
            ORDER BY stock_quantity ASC
            LIMIT 5
        """)

        df_top_drugs = query_df("""
            SELECT medication_name, category, total_dispensed_qty, prescription_count
            FROM gold_pharmacy
            ORDER BY total_dispensed_qty DESC
            LIMIT 5
        """)

        facts = [
            f"Identified {len(df_low_stock)} formulary items currently breaching safety stock thresholds.",
        ]
        for _, r in df_low_stock.iterrows():
            facts.append(
                f"Item: {r['medication_name']} ({r['category']}) | Current Stock: {r['stock_quantity']} units | "
                f"Reorder Level: {r['reorder_level']} | Days of Supply Remaining: {r['days_of_supply_remaining']} days"
            )

        if not df_top_drugs.empty:
            top_str = ", ".join([f"{r['medication_name']} ({r['total_dispensed_qty']} units)" for _, r in df_top_drugs.head(3).iterrows()])
            facts.append(f"Highest Volume Dispensed Drugs: {top_str}")

        predictions = []
        recommendations = []

        if not df_low_stock.empty:
            target_med = df_low_stock.iloc[0]
            pred_demand = predict_drug_demand(target_med["medication_id"])
            presc_action = get_pharmacy_prescriptive_actions(
                medication_name=target_med["medication_name"],
                current_stock=int(target_med["stock_quantity"]),
                reorder_level=int(target_med["reorder_level"]),
                days_of_supply=float(target_med["days_of_supply_remaining"]),
                predicted_demand=pred_demand.get("predicted_30d_demand", 300),
                unit_cost=float(target_med.get("unit_cost", 0.5)),
            )

            predictions.append(
                f"Projected 30-Day Demand for {target_med['medication_name']}: {pred_demand.get('predicted_30d_demand')} units. "
                f"Anticipated Inventory Shortfall: {pred_demand.get('projected_shortfall')} units without immediate procurement."
            )
            recommendations.extend(presc_action.get("action_steps", []))
        else:
            predictions.append("All formulary stock levels currently meet standard 30-day operating buffer requirements.")
            recommendations.append("Maintain standard weekly procurement audit cadence.")

        evidence = [
            "Source Table: gold_pharmacy (Aggregated inventory across hospital facilities)",
            "Model: Random Forest Pharmacy Demand Regressor v1.0.0",
            "Policy: POL-PHARM-002 (Pharmacy Inventory Replenishment Protocol)",
        ]

        return self.format_structured_response(
            facts=facts,
            predictions=predictions,
            recommendations=recommendations,
            evidence=evidence,
        )

    def analyze_laboratory_workload(self) -> Dict[str, Any]:
        """Analyze lab throughput, critical abnormal results, and capacity."""
        df_kpi = query_df("""
            SELECT
                COUNT(*) as total_investigations,
                SUM(is_abnormal) as abnormal_count,
                SUM(is_critical) as critical_count,
                ROUND(AVG(is_abnormal) * 100, 1) as abnormal_rate_pct,
                ROUND(AVG(is_critical) * 100, 1) as critical_rate_pct
            FROM gold_laboratory
        """).iloc[0]

        df_categories = query_df("""
            SELECT test_category, COUNT(*) as volume,
                   SUM(is_critical) as critical_flags
            FROM gold_laboratory
            GROUP BY test_category
            ORDER BY volume DESC
        """)

        facts = [
            f"Total Completed Diagnostic Investigations: {df_kpi['total_investigations']:,} tests",
            f"Abnormal Result Volume: {df_kpi['abnormal_count']:,} tests ({df_kpi['abnormal_rate_pct']}%)",
            f"Life-Critical Alarm Results: {df_kpi['critical_count']:,} tests ({df_kpi['critical_rate_pct']}%)",
        ]

        if not df_categories.empty:
            cat_str = ", ".join([f"{r['test_category']}: {r['volume']} tests" for _, r in df_categories.head(4).iterrows()])
            facts.append(f"Workload Distribution by Discipline: {cat_str}")

        top_cat = df_categories.iloc[0]["test_category"] if not df_categories.empty else "Biochemistry"
        plan = get_laboratory_prescriptive_plan(
            category=top_cat,
            projected_daily_tests=int(df_kpi["total_investigations"] // 120),
            critical_rate_pct=float(df_kpi["critical_rate_pct"]),
        )

        predictions = [
            f"Projected Investigation Volume for {top_cat}: Approaching peak load during 07:00-10:00 morning inpatient rounds.",
            f"Critical result incidence remains elevated at {df_kpi['critical_rate_pct']}%, requiring dedicated telephone escalation staffing.",
        ]

        recommendations = plan.get("recommended_staffing_actions", [])
        evidence = [
            "Source Table: gold_laboratory",
            "Policy: POL-LAB-001 (Critical Value Escalation Protocol)",
            "Policy: POL-LAB-002 (Biosafety & Analyzer Maintenance Standards)",
        ]

        return self.format_structured_response(
            facts=facts,
            predictions=predictions,
            recommendations=recommendations,
            evidence=evidence,
        )

    def process_query(self, user_query: str, username: str = "pharmacist_patel") -> Dict[str, Any]:
        """Process question and route to pharmacy or laboratory tools."""
        log_audit_event(
            username=username,
            role=self.role,
            action="AGENT_QUERY",
            resource="PharmaLab Agent",
            status="SUCCESS",
            details=user_query[:60],
        )

        q_lower = user_query.lower()

        # Check for RAG policy queries
        if any(w in q_lower for w in ["storage", "temperature", "cold chain", "safety", "handling", "biosafety", "spill", "tat", "policy"]):
            category = "Pharmacy" if self.role == "Pharmacist" else "Laboratory"
            rag_res = generate_grounded_answer(user_query, category=category)
            return self.format_structured_response(
                facts=[f"Queried Institutional {category} Protocols and Safety Standards."],
                predictions=["Policy and procedural inquiry."],
                recommendations=[rag_res.get("answer", "")],
                evidence=[f"Retrieved Document: {c['title']} ({c['filename']})" for c in rag_res.get("citations", [])],
            )

        if self.role == "Laboratory Technician" or any(w in q_lower for w in ["lab", "test", "workload", "critical", "analyzer", "biochemistry"]):
            return self.analyze_laboratory_workload()

        return self.analyze_pharmacy_risks()
