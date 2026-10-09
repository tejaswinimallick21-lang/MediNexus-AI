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
