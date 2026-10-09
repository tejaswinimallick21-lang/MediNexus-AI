"""
Prescriptive Hospital Executive Operations Rules for MediNexus AI.
"""

from typing import Dict, Any, List


def get_hospital_capacity_plan(
    occupancy_rate: float,
    projected_daily_admissions: int,
    average_los: float,
    total_beds: int = 500,
) -> Dict[str, Any]:
    """
    Generate prescriptive hospital surge capacity and resource management recommendations.
    """
    actions = []
    surge_tier = "LEVEL 1: NORMAL OPERATIONS"

    if occupancy_rate >= 0.90:
        surge_tier = "LEVEL 4: CRITICAL BED SURGE"
        actions.append("Convene Bed Management Escalation Huddle immediately.")
        actions.append("Expedite morning physician discharge rounds; target 30% discharges completed by 11:00 AM.")
        actions.append("Evaluate elective and non-urgent surgical admissions for 24-48 hour rescheduling.")
        actions.append("Activate step-down overflow beds in post-anesthesia care unit (PACU).")
    elif occupancy_rate >= 0.82:
        surge_tier = "LEVEL 3: HIGH OCCUPANCY ALERT"
        actions.append("Alert Emergency Department charge nurse regarding boarding times.")
        actions.append("Initiate discharge lounge utilization to free inpatient beds for incoming transfers.")
        actions.append("Review telemetry and step-down unit bed requests.")
    elif occupancy_rate >= 0.70:
        surge_tier = "LEVEL 2: ELEVATED BED DEMAND"
        actions.append("Monitor scheduled admissions against planned discharges.")
        actions.append("Ensure housekeeping turnover turnaround under 45 minutes.")
    else:
        surge_tier = "LEVEL 1: NORMAL OPERATIONS"
        actions.append("Maintain baseline staffing and admitting protocols.")

    return {
        "surge_tier": surge_tier,
        "current_occupancy_pct": round(occupancy_rate * 100, 1),
        "projected_admissions": projected_daily_admissions,
        "action_directives": actions,
        "throughput_assessment": (
            f"At {round(occupancy_rate * 100, 1)}% occupancy with {average_los:.1f} days average stay, "
            f"estimated bed turnover requirement is approximately {projected_daily_admissions} discharges/day."
        ),
    }
