"""
Prescriptive Laboratory Operations Rules for MediNexus AI.
"""

from typing import Dict, Any, List


def get_laboratory_prescriptive_plan(
    category: str,
    projected_daily_tests: int,
    critical_rate_pct: float,
    current_capacity: int = 150,
) -> Dict[str, Any]:
    """
    Generate actionable staffing, calibration, and reagent allocation recommendations for laboratory managers.
    """
    utilization_pct = round((projected_daily_tests / max(1, current_capacity)) * 100, 1)
    actions = []
    status = "OPTIMAL"

    if utilization_pct > 110:
        status = "CRITICAL_OVERLOAD"
        actions.append(f"Deploy PRN laboratory technician for evening shift on {category} analyzer bench.")
        actions.append("Fast-track emergency STAT orders and batch routine inpatient panels.")
        actions.append("Confirm emergency reagent replenishment buffer with vendor.")
    elif utilization_pct > 85:
        status = "HIGH_WORKLOAD"
        actions.append("Reallocate technician from outpatient blood collection to automated chemistry analyzers.")
        actions.append("Schedule equipment quality control (QC) and calibration prior to 07:00 morning inpatient rush.")
    else:
        status = "STABLE"
        actions.append("Workload within normal operational parameters. Proceed with standard preventive maintenance schedule.")

    if critical_rate_pct > 8.0:
        actions.append("Alert Laboratory Director: Critical result alert frequency is abnormally elevated.")

    return {
        "category": category,
        "operational_status": status,
        "utilization_percentage": utilization_pct,
        "recommended_staffing_actions": actions,
        "analyzer_capacity_assessment": (
            f"Expected daily volume ({projected_daily_tests} tests) represents {utilization_pct}% of single-shift rated analyzer capacity."
        ),
    }
