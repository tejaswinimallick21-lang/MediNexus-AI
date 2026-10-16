"""
Prescriptive Clinical Rules and Care Plan Recommendations for MediNexus AI.
Translates readmission risk and patient comorbidities into actionable physician decision support.
"""

from typing import Dict, Any, List

PRESCRIPTIVE_DISCLAIMER = "Clinical decision support guidance only. Licensed medical practitioners retain sole responsibility for patient care plans."


def get_clinical_prescription_plan(readmission_eval: Dict[str, Any], patient_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate tailored clinical follow-up recommendations based on ML risk assessment and patient clinical history.
    """
    risk_level = readmission_eval.get("risk_level", "LOW")
    prob = readmission_eval.get("probability", 0.0)

    recommendations = []
    actions = []
    rationale = []

    if risk_level == "HIGH":
        recommendations.append("Initiate Comprehensive Transitional Care Protocol (TCP)")
        actions.append("Schedule nurse telephone follow-up within 48 hours post-discharge.")
        actions.append("Mandate specialist follow-up consultation within 7 days.")
        actions.append("Perform complete medication reconciliation before discharge to prevent adverse drug events.")
        rationale.append(f"Patient exhibits high 30-day readmission probability ({prob}%). Multidisciplinary follow-up significantly reduces acute bounce-backs.")

        if patient_profile.get("has_heart_failure") == 1:
            actions.append("Enroll in outpatient cardiac telemetry / daily weight monitoring.")
            rationale.append("Congestive heart failure is strongly correlated with early decompensation.")

        if patient_profile.get("has_diabetes") == 1:
            actions.append("Verify home blood glucose monitoring and review insulin/antidiabetic titration.")

        if patient_profile.get("critical_lab_count", 0) >= 1:
            actions.append("Order repeat metabolic panel and complete blood count within 5 days.")

    elif risk_level == "MODERATE":
        recommendations.append("Standard Discharge with Targeted Monitoring")
        actions.append("Schedule routine primary care follow-up within 10-14 days.")
        actions.append("Provide patient with printed disease-specific warning signs checklist.")
        actions.append("Ensure 30-day prescription refill supply is ready at discharge.")
        rationale.append(f"Moderate readmission risk ({prob}%). Preventative outpatient contact mitigates deterioration.")

    else:
        recommendations.append("Standard Low-Risk Discharge Protocol")
        actions.append("Follow-up appointment as needed (PRN) with primary care provider.")
        actions.append("Standard post-discharge health education and symptom management.")
        rationale.append(f"Patient demonstrates low readmission probability ({prob}%). Standard outpatient care pathway appropriate.")

    return {
        "care_tier": f"{risk_level} Risk Management Pathway",
        "primary_recommendation": recommendations[0] if recommendations else "Standard Clinical Observation",
        "actionable_checklist": actions,
        "clinical_rationale": rationale,
        "disclaimer": PRESCRIPTIVE_DISCLAIMER,
    }


def get_oncology_care_plan(risk_level: str, treatment_status: str, stage: str = None) -> Dict[str, Any]:
    """
    Care pathway for a cancer patient from their 12-month mortality-risk band and where they are in
    treatment. Rule text follows common oncology practice (early palliative care for advanced
    disease, a blood count before each systemic cycle, survivorship follow-up every 3-6 months).
    """
    if treatment_status == "Deceased":
        return {"care_tier": "Closed record", "primary_recommendation": "No active care plan: the patient has died.",
                "actionable_checklist": [], "clinical_rationale": [], "disclaimer": PRESCRIPTIVE_DISCLAIMER}
    if risk_level == "HIGH" or treatment_status == "Hospice":
        tier, primary = "Palliative and supportive care pathway", "Hold a goals-of-care conversation and refer to palliative care"
        checklist = [
            "Refer to the palliative care team for symptom and goals-of-care review.",
            "Review the case at the next multidisciplinary tumour board.",
            "Confirm an advance care plan and the patient's preferred place of care.",
            "Screen for pain, nutrition and psychosocial needs at every visit.",
        ]
        why = [f"12-month mortality risk is in the top band{f' (stage {stage})' if stage else ''}; early palliative care improves quality of life in advanced cancer."]
    elif treatment_status in ("In treatment", "Awaiting treatment"):
        tier, primary = "Active treatment pathway", "Keep systemic therapy on schedule with safety checks before each cycle"
        checklist = [
            "Full blood count and metabolic panel within 7 days before every cycle.",
            "Antiemetic and growth-factor support as per the regimen.",
            "Restaging imaging at the interval set by the regimen protocol.",
            "Tumour marker with each cycle where one is followed for this cancer.",
        ]
        why = ["The patient is starting or receiving treatment; most avoidable harm happens between cycles."]
        if treatment_status == "Awaiting treatment":
            checklist.insert(0, "Book the first treatment: aim for treatment within 30 days of diagnosis.")
    else:
        tier, primary = "Survivorship and surveillance pathway", "Follow up every 3-6 months and watch for recurrence"
        checklist = [
            "Follow-up visit every 3-6 months for the first years after treatment.",
            "Tumour marker and surveillance imaging per guideline for this cancer type.",
            "Survivorship care plan shared with primary care.",
            "Manage late effects of treatment and comorbidities.",
        ]
        why = ["Treatment is complete or not needed now; the main risk is recurrence."]
    return {"care_tier": tier, "primary_recommendation": primary, "actionable_checklist": checklist,
            "clinical_rationale": why, "disclaimer": PRESCRIPTIVE_DISCLAIMER}
