"""
Prescriptive Pharmacy Rules and Procurement Engine for MediNexus AI.
"""

from typing import Dict, Any, List


def get_pharmacy_prescriptive_actions(
    medication_name: str,
    current_stock: int,
    reorder_level: int,
    days_of_supply: float,
    predicted_demand: int,
    unit_cost: float,
) -> Dict[str, Any]:
    """
    Generate actionable pharmacy procurement orders and inventory management advice.
    """
    shortfall = max(0, predicted_demand - current_stock)
    is_critical_shortage = days_of_supply < 7.0 or current_stock < (reorder_level * 0.5)

    actions = []
    urgency = "LOW"
    target_order_qty = 0

    if is_critical_shortage:
        urgency = "URGENT"
        target_order_qty = max(shortfall + reorder_level, reorder_level * 2)
        actions.append(f"Issue IMMEDIATE emergency procurement order for {target_order_qty} units of {medication_name}.")
        actions.append("Notify prescribing physicians to consider equivalent therapeutic alternatives if available.")
        actions.append("Restructure inpatient dispensing to standard unit-dose rounds to minimize ward stock wastage.")
    elif current_stock <= reorder_level:
        urgency = "ELEVATED"
        target_order_qty = max(shortfall + reorder_level, reorder_level)
        actions.append(f"Include {target_order_qty} units in standard weekly wholesale replenishment purchase order.")
        actions.append("Review consumption rate by department over previous 14 days.")
    else:
        urgency = "NORMAL"
        actions.append("Current inventory exceeds reorder safety buffer. Maintain standard monitoring cycle.")

    estimated_order_cost = round(target_order_qty * unit_cost, 2)

    return {
        "medication_name": medication_name,
        "urgency_level": urgency,
        "recommended_order_quantity": target_order_qty,
        "estimated_procurement_cost": estimated_order_cost,
        "action_steps": actions,
        "buffer_assessment": (
            f"Current stock provides approximately {days_of_supply:.1f} days of supply based on projected burn rate."
        ),
    }
