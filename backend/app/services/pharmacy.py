"""Pharmacy & Supply Chain services (hcp role)."""

from datetime import datetime
from typing import List, Optional

from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.core.users import UserRecord
from backend.app.schemas.operations import ClassOutlook, ClassOutlookRow, DemandForecast, ForecastMeta, PharmacyKpis, PurchaseOrderOut, StockLine
from src.ml.predict import forecast_drug_class_demand, predict_drug_demand
from src.prescriptive.pharmacy_rules import get_pharmacy_prescriptive_actions
from src.security.audit import log_audit_event
from src.utils.database import execute_query, query_df_strict
from src.utils.helpers import generate_uuid

RISK_ORDER = "CASE stockout_risk WHEN 'High Risk' THEN 0 WHEN 'Moderate Risk' THEN 1 ELSE 2 END"
MAX_ORDER_UNITS = 100_000


def get_kpis() -> PharmacyKpis:
    r = query_df_strict(f"""
        SELECT COUNT(*) AS lines,
               COUNT(*) FILTER (WHERE stockout_risk = 'High Risk') AS high,
               COUNT(*) FILTER (WHERE stockout_risk = 'Moderate Risk') AS moderate,
               SUM(TRY_CAST(total_dispensed_qty AS DOUBLE)) AS dispensed,
               (SELECT COUNT(*) FROM gold_prescriptions WHERE status = 'Active') AS active_rx
        FROM gold_pharmacy
    """).iloc[0]
    return PharmacyKpis(
        stock_lines=int(r["lines"]), high_risk_lines=int(r["high"]), moderate_risk_lines=int(r["moderate"]),
        dispensed_units_180d=int(round(float(r["dispensed"] or 0))), active_prescriptions=int(r["active_rx"]),
    )


def _stock_rows(df) -> List[StockLine]:
    def num(v):
        return None if v is None or v != v else float(v)

    return [
        StockLine(
            inventory_id=r.inventory_id, medication_id=r.medication_id, medication_name=r.medication_name,
            category=r.category if isinstance(r.category, str) else None,
            hospital_id=r.hospital_id, hospital_name=r.hospital_name if isinstance(r.hospital_name, str) else None,
            stock_quantity=int(float(r.stock_quantity)), reorder_level=int(float(r.reorder_level)),
            days_of_supply=None if num(r.days_of_supply_remaining) is None or num(r.days_of_supply_remaining) >= 999 else round(num(r.days_of_supply_remaining), 1),
            stockout_risk=r.stockout_risk,
        )
        for r in df.itertuples()
    ]


STOCK_COLUMNS = """inventory_id, medication_id, medication_name, category, hospital_id, hospital_name,
                   stock_quantity, reorder_level, days_of_supply_remaining, stockout_risk"""


def list_stock(params: PageParams, risk: Optional[str] = None, search: Optional[str] = None) -> Page[StockLine]:
    where, args = ["1=1"], []
    if risk:
        where.append("stockout_risk = ?")
        args.append(risk)
    if search:
        where.append("(medication_name ILIKE ? OR hospital_name ILIKE ?)")
        args += [f"%{search}%", f"%{search}%"]
    df = query_df_strict(
        f"""SELECT {STOCK_COLUMNS} FROM gold_pharmacy WHERE {' AND '.join(where)}
            ORDER BY {RISK_ORDER}, TRY_CAST(days_of_supply_remaining AS DOUBLE) ASC, inventory_id LIMIT ? OFFSET ?""",
        args + [params.limit + 1, params.offset],
    )
    return build_page(_stock_rows(df), params)


def get_risk_by_category() -> List[dict]:
    df = query_df_strict("""
        SELECT coalesce(category, 'Other') AS category,
               COUNT(*) FILTER (WHERE stockout_risk = 'High Risk') AS high,
               COUNT(*) FILTER (WHERE stockout_risk = 'Moderate Risk') AS moderate,
               COUNT(*) FILTER (WHERE stockout_risk = 'Safe') AS safe
        FROM gold_pharmacy GROUP BY 1 ORDER BY high DESC, moderate DESC LIMIT 10
    """)
    return [{"category": r.category, "high": int(r.high), "moderate": int(r.moderate), "safe": int(r.safe)} for r in df.itertuples()]


def _stock_line(inventory_id: str):
    df = query_df_strict(f"SELECT {STOCK_COLUMNS}, unit_cost FROM gold_pharmacy WHERE inventory_id = ? LIMIT 1", [inventory_id])
    if df.empty:
        raise APIError(404, "stock_line_not_found", f"No stock line {inventory_id}.")
    return df.iloc[0]


def get_demand_forecast(inventory_id: str) -> DemandForecast:
    line = _stock_line(inventory_id)
    demand = predict_drug_demand(line["medication_id"], hospital_id=line["hospital_id"])
    if demand.get("status") != "SUCCESS":
        raise APIError(404, "forecast_unavailable", demand.get("message", "Forecast unavailable."))
    dos = float(line["days_of_supply_remaining"]) if line["days_of_supply_remaining"] == line["days_of_supply_remaining"] else 999.0
    plan = get_pharmacy_prescriptive_actions(
        medication_name=demand["medication_name"],
        current_stock=demand["current_stock"],
        reorder_level=int(float(line["reorder_level"])),
        days_of_supply=dos,
        predicted_demand=demand["predicted_30d_demand"],
        unit_cost=float(line["unit_cost"] or 0),
    )
    return DemandForecast(
        inventory_id=inventory_id,
        medication_name=demand["medication_name"],
        hospital_name=demand.get("hospital_name"),
        current_stock=demand["current_stock"],
        dispensed_last_30d=demand["dispensed_last_30d"],
        predicted_30d_demand=demand["predicted_30d_demand"],
        projected_shortfall=demand["projected_shortfall"],
        urgency=plan["urgency_level"],
        recommended_order_quantity=plan["recommended_order_quantity"],
        estimated_procurement_cost=plan["estimated_procurement_cost"],
        actions=plan["action_steps"],
        buffer_assessment=plan["buffer_assessment"] if dos < 999 else "No dispensing in the last 180 days; stock is not being drawn down.",
        forecast=ForecastMeta(**{k: demand.get(k) for k in ForecastMeta.model_fields}),
    )


def get_class_outlook() -> ClassOutlook:
    """Network demand outlook per drug class (trained on SIMULATED operations data, labelled as such)."""
    f = forecast_drug_class_demand()
    rows = sorted(
        (
            ClassOutlookRow(
                drug_class=r["group"], forecast_daily_units=r["forecast_daily"], last_7d_daily_units=r["last_7d_daily"],
                change_pct=round((r["forecast_daily"] - r["last_7d_daily"]) / max(1e-9, r["last_7d_daily"]) * 100, 1),
            )
            for r in f["forecasts"]
        ),
        key=lambda r: r.forecast_daily_units,
        reverse=True,
    )
    return ClassOutlook(simulated_data=True, as_of=f["as_of"], items=rows, forecast=ForecastMeta(**{k: f.get(k) for k in ForecastMeta.model_fields}))


def _ensure_po_table() -> None:
    execute_query("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id VARCHAR, inventory_id VARCHAR, medication_name VARCHAR, quantity INTEGER,
            estimated_cost DOUBLE, status VARCHAR, created_by VARCHAR, created_at TIMESTAMP
        )
    """)


def create_purchase_order(inventory_id: str, quantity: int, user: UserRecord) -> PurchaseOrderOut:
    if quantity <= 0 or quantity > MAX_ORDER_UNITS:
        raise APIError(422, "invalid_quantity", f"Quantity must be between 1 and {MAX_ORDER_UNITS:,}.")
    line = _stock_line(inventory_id)
    now = datetime.now()
    po = PurchaseOrderOut(
        po_id=generate_uuid("PO").upper(),
        inventory_id=inventory_id,
        medication_name=str(line["medication_name"]),
        quantity=quantity,
        estimated_cost=round(quantity * float(line["unit_cost"] or 0), 2),
        status="SUBMITTED",
        created_at=now.isoformat(timespec="seconds"),
    )
    _ensure_po_table()
    execute_query(
        "INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [po.po_id, inventory_id, po.medication_name, quantity, po.estimated_cost, po.status, user.email, now],
    )
    log_audit_event(
        username=user.email, role=user.role, action="PROCUREMENT_ORDER", resource=inventory_id, status="SUCCESS",
        details=f"PO {po.po_id}: {quantity} units of {po.medication_name}",
    )
    return po
