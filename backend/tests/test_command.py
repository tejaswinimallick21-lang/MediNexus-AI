"""
Analyst Command Center: contracts, access and the what-if simulation's behaviour.
"""

from backend.app.schemas.command import HospitalOption, ModelMonitorRow, ReadmissionEconomics, WhatIfIn, WhatIfResult
from backend.app.services import command
from backend.tests.conftest import assert_contract, assert_error
from backend.tests.test_operations import contract_list
from src.utils.database import query_df_strict


def test_command_center_access(login, client):
    assert_error(client.get("/api/command/models"), 401, "not_authenticated")
    assert_error(login("hcp").get("/api/command/models"), 403, "forbidden")


def test_hospitals_contract(login):
    rows = contract_list(login("analyst").get("/api/command/hospitals"), HospitalOption, "command_hospitals")
    assert len(rows) == 91
    assert rows[0]["served_pct"] <= rows[-1]["served_pct"]  # most pressured first


def test_what_if_contract(login):
    body = {"period": "last_90", "extra_visits_per_physician": 3, "extra_physicians": 0, "demand_change_pct": 0}
    res = assert_contract(login("analyst").post("/api/command/what-if", json=body), WhatIfResult, "command_what_if")
    assert res["simulated_data"] is True and res["days"] == 90 and len(res["daily"]) == 90
    assert res["scenario"]["served"] >= res["baseline"]["served"]


def test_what_if_rejects_out_of_range(login):
    r = login("analyst").post("/api/command/what-if", json={"extra_visits_per_physician": 99})
    assert r.status_code == 422


def test_what_if_unknown_hospital(login):
    assert_error(login("admin").post("/api/command/what-if", json={"hospital_id": "NOPE"}), 404, "hospital_not_found")


def test_no_change_scenario_replays_the_baseline():
    hospital = command.list_hospitals()[0].hospital_id
    res = command.run_what_if(WhatIfIn(hospital_id=hospital, period="last_365"))
    assert res.scenario == res.baseline and res.net_impact == 0


def test_more_capacity_reduces_backlog_and_demand_raises_it():
    hospital = command.list_hospitals()[0].hospital_id  # the most pressured hospital has a real waiting list
    base = command.run_what_if(WhatIfIn(hospital_id=hospital, period="last_365"))
    more_docs = command.run_what_if(WhatIfIn(hospital_id=hospital, period="last_365", extra_physicians=10))
    surge = command.run_what_if(WhatIfIn(hospital_id=hospital, period="last_365", demand_change_pct=20))
    latest = str(query_df_strict("SELECT max(CAST(date AS DATE)) AS d FROM sim_outpatient_daily").iloc[0]["d"])[:10]
    assert base.period_end == latest  # the replay ends on the latest released simulated day
    assert more_docs.scenario.avg_backlog < base.baseline.avg_backlog
    assert more_docs.scenario.staffing_cost > base.baseline.staffing_cost
    assert surge.scenario.avg_backlog > base.baseline.avg_backlog
    assert surge.scenario.lost_to_follow_up > base.baseline.lost_to_follow_up


def test_readmission_economics_contract(login):
    body = assert_contract(login("analyst").get("/api/command/readmission-economics"), ReadmissionEconomics, "command_readmission_economics")
    assert body["discharges"] > 0 and 0 < body["model_capture_pct"] <= 100
    assert body["readmission_rate_pct"] == round(body["unplanned_readmissions"] / body["discharges"] * 100, 2)


def test_model_monitor_contract(login):
    rows = contract_list(login("admin").get("/api/command/models"), ModelMonitorRow, "command_models")
    names = {r["model_name"] for r in rows}
    assert {"readmission_risk_model", "outpatient_demand_model"} <= names
    assert not any(n.startswith("test_") for n in names)
    sim = next(r for r in rows if r["model_name"] == "outpatient_demand_model")
    assert sim["data_source"] == "Simulated ops data"
