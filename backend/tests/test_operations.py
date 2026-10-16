"""
Laboratory, Pharmacy, Executive and copilot endpoints: contracts, access and service behaviour.
"""

from typing import List

import pytest
from pydantic import TypeAdapter

from backend.app.core.pagination import Page
from backend.app.schemas.operations import (
    AgentReply,
    CategoryWorkload,
    CostByType,
    CriticalAlert,
    DemandForecast,
    ExecutiveForecasts,
    ExecutiveKpis,
    LabCapacityPlan,
    LabKpis,
    PharmacyKpis,
    PurchaseOrderOut,
    StageMixRow,
    StockLine,
    SurvivalOverview,
    TrendPoint,
)
from backend.app.services import executive as exec_svc
from backend.tests.conftest import assert_contract, assert_error
from src.analytics.metrics import compute_lab_kpis
from src.utils.database import execute_query


def contract_list(response, model, fixture):
    """List payloads: validate every item with a TypeAdapter, then save the fixture."""
    from backend.tests.conftest import FIXTURE_DIR
    import json

    assert response.status_code == 200, response.text
    payload = response.json()
    TypeAdapter(List[model]).validate_python(payload)
    (FIXTURE_DIR / f"{fixture}.json").write_text(json.dumps(payload[:50], indent=2), encoding="utf-8")
    return payload


# ---- Laboratory -------------------------------------------------------------------------------

def test_lab_kpis_match_legacy(login):
    body = assert_contract(login("hcp").get("/api/lab/kpis"), LabKpis, "lab_kpis")
    legacy = compute_lab_kpis()
    for key in ("total_tests", "abnormal_tests", "critical_tests", "abnormal_pct", "critical_pct"):
        assert body[key] == pytest.approx(legacy[key]), key


def test_lab_workload_contract(login):
    contract_list(login("hcp").get("/api/lab/workload-by-category"), CategoryWorkload, "lab_workload")


def test_lab_daily_volume_contract(login):
    contract_list(login("hcp").get("/api/lab/daily-volume", params={"days": 60}), TrendPoint, "lab_daily_volume")


def test_lab_critical_alerts_contract(login):
    body = assert_contract(login("hcp").get("/api/lab/critical-alerts", params={"limit": 5}), Page[CriticalAlert], "lab_critical_alerts")
    assert len(body["items"]) == 5


def test_lab_capacity_plan_contract(login):
    c = login("hcp")
    category = c.get("/api/lab/categories").json()[0]
    body = assert_contract(c.get(f"/api/lab/categories/{category}/capacity-plan"), LabCapacityPlan, "lab_capacity_plan")
    assert body["forecast"]["serving_method"] in {"model", "surge_aware", "baseline_naive7"}


def test_lab_unknown_category(login):
    assert_error(login("hcp").get("/api/lab/categories/Nope/capacity-plan"), 404, "unknown_category")


# ---- Pharmacy ---------------------------------------------------------------------------------

def test_pharmacy_kpis_contract(login):
    assert_contract(login("hcp").get("/api/pharmacy/kpis"), PharmacyKpis, "pharmacy_kpis")


def test_pharmacy_stock_contract_and_risk_filter(login):
    body = assert_contract(login("hcp").get("/api/pharmacy/stock", params={"limit": 10, "risk": "High Risk"}), Page[StockLine], "pharmacy_stock")
    assert body["items"] and all(i["stockout_risk"] == "High Risk" for i in body["items"])


def test_pharmacy_class_outlook_contract(login):
    from backend.app.schemas.operations import ClassOutlook

    body = assert_contract(login("hcp").get("/api/pharmacy/class-outlook"), ClassOutlook, "pharmacy_class_outlook")
    assert body["simulated_data"] is True and len(body["items"]) >= 5


def test_pharmacy_forecast_contract(login):
    c = login("hcp")
    inv = c.get("/api/pharmacy/stock", params={"limit": 1}).json()["items"][0]["inventory_id"]
    body = assert_contract(c.get(f"/api/pharmacy/stock/{inv}/forecast"), DemandForecast, "pharmacy_forecast")
    assert body["projected_shortfall"] == max(0, body["predicted_30d_demand"] - body["current_stock"])


def test_purchase_order_is_created_and_validated(login):
    c = login("hcp")
    inv = c.get("/api/pharmacy/stock", params={"limit": 1}).json()["items"][0]["inventory_id"]
    body = assert_contract(c.post("/api/pharmacy/purchase-orders", json={"inventory_id": inv, "quantity": 12}), PurchaseOrderOut, "pharmacy_purchase_order", status=201)
    execute_query("DELETE FROM purchase_orders WHERE po_id = ?", [body["po_id"]])  # tests never leave data behind
    assert_error(c.post("/api/pharmacy/purchase-orders", json={"inventory_id": inv, "quantity": 0}), 422, "invalid_quantity")
    assert_error(c.post("/api/pharmacy/purchase-orders", json={"inventory_id": "INV_NOPE", "quantity": 1}), 404, "stock_line_not_found")


# ---- Executive --------------------------------------------------------------------------------

def test_executive_kpis_contract(login):
    body = assert_contract(login("analyst").get("/api/executive/kpis"), ExecutiveKpis, "executive_kpis")
    assert body["hospitals"] > 1 and 0 < body["living_patients"] <= body["patients"]
    assert 0 < body["five_year_survival_pct"] < 100


def test_executive_outcome_contracts(login):
    c = login("analyst")
    contract_list(c.get("/api/executive/diagnoses-trend", params={"months": 24}), TrendPoint, "executive_diagnoses_trend")
    surv = assert_contract(c.get("/api/executive/survival"), SurvivalOverview, "executive_survival")
    stage = {cv["label"]: cv for cv in surv["curves"] if cv["kind"] == "stage"}
    five = {k: next(p["survival_pct"] for p in v["points"] if p["month"] == 60) for k, v in stage.items()}
    assert five["Stage I"] > five["Stage IV"]  # survival falls with stage
    assert all(cv["points"][0]["survival_pct"] == 100 for cv in surv["curves"])
    mix = contract_list(c.get("/api/executive/stage-mix"), StageMixRow, "executive_stage_mix")
    assert sum(r["stage_i"] + r["stage_ii"] + r["stage_iii"] + r["stage_iv"] for r in mix) > 0
    contract_list(c.get("/api/executive/cost-by-type"), CostByType, "executive_cost_by_type")


def test_executive_forecasts_report_real_registry_metrics(login):
    body = assert_contract(login("analyst").get("/api/executive/forecasts"), ExecutiveForecasts, "executive_forecasts")
    assert {r["service"] for r in body["treatment"]} == {"Infusion chairs (chemo / immuno / targeted)", "Radiation sessions"}
    mortality = next(m for m in body["models"] if m["model"] == "Death within 12 months")
    assert "Stage + type" in mortality["baseline"]
    assert not any("readmission" in m["model"].lower() for m in body["models"])


def test_verdict_helper():
    assert exec_svc._verdict(0.80, 0.68) == "Beats baseline"
    assert exec_svc._verdict(9.4, 5.6, higher_is_better=False) == "Baseline wins — baseline served"


# ---- Access & copilots ------------------------------------------------------------------------

@pytest.mark.parametrize("role,path,status", [
    ("analyst", "/api/lab/kpis", 403),
    ("analyst", "/api/pharmacy/kpis", 403),
    ("hcp", "/api/executive/kpis", 403),
    ("admin", "/api/lab/kpis", 200),
    ("admin", "/api/executive/kpis", 200),
])
def test_role_access(login, role, path, status):
    assert login(role).get(path).status_code == status


def test_copilot_chat_contract(login):
    body = assert_contract(
        login("analyst").post("/api/agents/healthanalyst/chat", json={"message": "How does survival differ by stage?"}),
        AgentReply,
        "agent_reply",
    )
    assert body["facts"] or body["recommendations"]


def test_copilot_role_enforced(login):
    assert_error(login("analyst").post("/api/agents/medicare/chat", json={"message": "hello"}), 403, "forbidden")
    assert_error(login("hcp").post("/api/agents/medicare/chat", json={"message": "   "}), 422, "empty_message")
