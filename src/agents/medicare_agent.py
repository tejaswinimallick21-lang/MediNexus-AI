"""
MediCare Agent for MediNexus AI.
Role-specific AI agent for Doctors: patient summaries, risk predictions, lab trends, and clinical decision support.
"""

import re
from typing import Dict, Any, List
import pandas as pd

from src.agents.base_agent import BaseHealthcareAgent
from src.utils.database import query_df
from src.ml.predict import predict_patient_readmission, predict_patient_los
from src.prescriptive.clinical_rules import get_clinical_prescription_plan
from src.rag.knowledge_base import generate_grounded_answer
from src.security.audit import log_audit_event


class MediCareAgent(BaseHealthcareAgent):
    """
    Physician Decision Support and Patient Intelligence Agent.
    """

    def __init__(self):
        super().__init__(
            agent_name="MediCare Agent",
            role="Doctor",
            system_prompt=(
                "You are MediCare Agent, an AI decision-support clinical copilot for physicians. "
                "Never diagnose a patient or recommend off-label unverified care. "
                "Ground all statements strictly in the retrieved Patient 360 data, laboratory trends, "
                "ML risk scores, and institutional guidelines. "
                "Always separate FACTS, PREDICTIONS, and RECOMMENDATIONS."
            ),
        )

    def search_patient_record(self, term: str) -> pd.DataFrame:
        """Search patient by ID or name in Gold layer."""
        term_clean = term.strip()
        sql = """
            SELECT patient_id, name, age, gender, blood_group,
                   total_admissions, clinical_risk_tier, comorbidities_list,
                   abnormal_lab_count, critical_lab_count
            FROM gold_patient_360
            WHERE patient_id ILIKE ? OR name ILIKE ?
            LIMIT 5
        """
        return query_df(sql, [f"%{term_clean}%", f"%{term_clean}%"])

    def get_patient_summary(self, patient_id: str) -> Dict[str, Any]:
        """Retrieve full patient profile, ML predictions, and prescriptive recommendations."""
        df_p = query_df("SELECT * FROM gold_patient_360 WHERE patient_id = ?", [patient_id])
        if df_p.empty:
            return {"error": f"Patient {patient_id} not found."}

        p = df_p.iloc[0].to_dict()

        # ML predictions
        readm_pred = predict_patient_readmission(patient_id)
        los_pred = predict_patient_los(patient_id)

        # Prescriptive clinical plan
        care_plan = get_clinical_prescription_plan(readm_pred, p)

        # Recent diagnoses
        df_dx = query_df(
            "SELECT icd10_code, diagnosis_description, diagnosis_type, severity FROM gold_clinical WHERE patient_id = ? ORDER BY admission_date DESC LIMIT 4",
            [patient_id],
        )

        # Recent abnormal labs
        df_labs = query_df(
            "SELECT test_name, test_value, unit, abnormal_flag, test_date FROM gold_laboratory WHERE patient_id = ? AND is_abnormal = 1 ORDER BY test_date DESC LIMIT 5",
            [patient_id],
        )

        # Active medications
        df_meds = query_df(
            "SELECT medication_name, dosage, frequency, status FROM gold_prescriptions WHERE patient_id = ? LIMIT 5",
            [patient_id],
        )

        facts = [
            f"Patient: {p.get('name')} (ID: {patient_id}) | Age: {p.get('age')} | Gender: {p.get('gender')} | Blood Group: {p.get('blood_group')}",
            f"Lifetime Inpatient Encounters: {p.get('total_admissions')} admissions (Total LOS: {p.get('total_los')} days)",
            f"Documented Comorbidities: {p.get('comorbidities_list', 'None recorded')}",
            f"Laboratory Profile: {p.get('total_lab_tests')} tests recorded, with {p.get('abnormal_lab_count')} abnormal results and {p.get('critical_lab_count')} critical flags",
            f"Active Prescriptions: {p.get('active_prescriptions_count')} active medications",
        ]

        if not df_dx.empty:
            dx_summary = "; ".join([f"{r['diagnosis_description']} ({r['severity']})" for _, r in df_dx.iterrows()])
            facts.append(f"Recent Diagnoses: {dx_summary}")

        if not df_labs.empty:
            lab_summary = "; ".join([f"{r['test_name']}={r['test_value']} {r['unit']} [{r['abnormal_flag']}]" for _, r in df_labs.iterrows()])
            facts.append(f"Recent Abnormal Labs: {lab_summary}")

        predictions = [
            f"30-Day Readmission Risk: {readm_pred.get('risk_level')} ({readm_pred.get('probability')}% probability, {readm_pred.get('confidence')})",
            f"Expected Inpatient Length of Stay (LOS): {los_pred.get('predicted_los_days', 'N/A')} days (CI: {los_pred.get('confidence_interval', 'N/A')})",
            f"Observed Contributing Risk Factors: {', '.join(readm_pred.get('contributing_factors', []))}",
        ]

        recommendations = [
            f"Care Pathway: {care_plan.get('primary_recommendation')}",
        ]
        recommendations.extend([f"Action: {item}" for item in care_plan.get("actionable_checklist", [])[:3]])

        evidence = [
            f"Source Table: gold_patient_360 (Record: {patient_id})",
            f"Model: {readm_pred.get('model_version', 'v1.2.0')} Random Forest Classifier (Trained on Gold Risk Features)",
            "Clinical Guideline: CPG-CLIN-001 (Transitional Care Protocol)",
        ]

        return self.format_structured_response(
            facts=facts,
            predictions=predictions,
            recommendations=recommendations,
            evidence=evidence,
            raw_context={"patient": p, "readmission": readm_pred, "los": los_pred},
            notes=readm_pred.get("disclaimer", ""),
        )

    def process_query(self, user_query: str, username: str = "dr_chen") -> Dict[str, Any]:
        """
        Route doctor's free-text inquiry to appropriate clinical tools.
        """
        log_audit_event(
            username=username,
            role="Doctor",
            action="AGENT_QUERY",
            resource="MediCare Agent",
            status="SUCCESS",
            details=user_query[:60],
        )

        # Check if query references a specific patient ID like P_00012 or P12
        p_match = re.search(r"\b(P_?\d{2,5})\b", user_query, re.IGNORECASE)
        if p_match:
            raw_p_id = p_match.group(1).upper()
            # Normalize to P_00000 format if needed
            digits = re.findall(r"\d+", raw_p_id)[0]
            normalized_p_id = f"P_{int(digits):05d}"
            return self.get_patient_summary(normalized_p_id)

        # Check for policy/guideline question
        if any(w in user_query.lower() for w in ["guideline", "policy", "protocol", "discharge", "hypertension", "diabetes", "heart failure"]):
            rag_res = generate_grounded_answer(user_query, category="Clinical Guidelines")
            return self.format_structured_response(
                facts=["Queried Institutional Clinical Practice Guidelines & Hospital Policies."],
                predictions=["No patient-specific ML prediction requested."],
                recommendations=[rag_res.get("answer", "")],
                evidence=[f"Retrieved Document: {c['title']} ({c['filename']})" for c in rag_res.get("citations", [])],
                notes="Decision support reference from institutional policy repository.",
            )

        # Default: high risk patient cohort summary
        df_high_risk = query_df(
            "SELECT patient_id, name, age, gender, comorbidities_list, clinical_risk_tier FROM gold_patient_360 WHERE clinical_risk_tier = 'High' LIMIT 5"
        )
        facts = [
            f"Retrieved top {len(df_high_risk)} highest-risk patients currently monitored under Gold intelligence layer.",
        ]
        for _, r in df_high_risk.iterrows():
            facts.append(f"Patient {r['patient_id']} ({r['name']}, {r['age']}yo {r['gender']}) - Comorbidities: {r['comorbidities_list']}")

        predictions = [
            "Patients listed above exhibit statistically elevated risk for 30-day post-discharge readmission.",
        ]
        recommendations = [
            "Specify a patient ID (e.g. 'P_00005') to inspect deep Patient 360, ML risk predictions, and prescriptive care checklists.",
            "Review inpatient discharge readiness against Transitional Care Protocol (CPG-CLIN-001).",
        ]
        evidence = ["Source Table: gold_patient_360 (Filtered: clinical_risk_tier='High')"]

        return self.format_structured_response(
            facts=facts,
            predictions=predictions,
            recommendations=recommendations,
            evidence=evidence,
        )
