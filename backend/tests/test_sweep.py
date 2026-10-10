"""
Nexa morning sweep: detects unattended work, proposes (never executes), never duplicates.
Runs with the rules provider (template justifications), so no paid LLM is called.
"""

from datetime import datetime

import pytest

from backend.app.agents import providers, sweep
from backend.app.schemas.actions import SweepStatus
from backend.tests.conftest import assert_contract, assert_error
from src.utils.database import execute_query, query_df_strict


@pytest.fixture()
def runs():
    ids = []
    yield ids
    for run_id in ids:
        tag = f"sweep:{run_id}"
        execute_query("DELETE FROM care_tasks WHERE source_action_id IN (SELECT action_id FROM agent_actions WHERE session_id = ?)", [tag])
        execute_query("DELETE FROM agent_actions WHERE session_id = ?", [tag])
        execute_query("DELETE FROM sweep_runs WHERE run_id = ?", [run_id])


def test_sweep_proposes_each_kind_once(runs, monkeypatch):
    monkeypatch.setattr(sweep, "MAX_PROPOSALS", 9)
    first = sweep.run_sweep("manual")
    runs.append(first["run_id"])
    assert first["proposed"] > 0 and first["ai_used"] is False
    assert set(first["by_kind"]) == {"follow_up", "purchase_order", "lab_escalation"}
    assert all(v > 0 for v in first["by_kind"].values()), first["by_kind"]  # every kind represented within the cap

    rows = query_df_strict("SELECT kind, status, reason, payload, requested_by FROM agent_actions WHERE session_id = ?", [f"sweep:{first['run_id']}"])
    assert (rows["status"] == "pending").all() and (rows["requested_by"] == "nexa-sweep@medinexus.org").all()
    assert rows["reason"].str.len().min() > 40  # each proposal carries an evidence-based justification
    assert "Approving" in rows["reason"].iloc[0]

    second = sweep.run_sweep("manual")
    runs.append(second["run_id"])
    keys_first = set(rows["payload"])
    keys_second = set(query_df_strict("SELECT payload FROM agent_actions WHERE session_id = ?", [f"sweep:{second['run_id']}"])["payload"])
    assert not keys_first & keys_second  # nothing proposed twice while pending


def test_ai_failure_falls_back_to_template(runs, monkeypatch):
    def broken(*a, **k):
        raise providers.ProviderError("quota")

    monkeypatch.setattr(providers, "active_provider", lambda: "openai")
    monkeypatch.setattr(providers, "complete", broken)
    monkeypatch.setattr(sweep, "MAX_PROPOSALS", 2)
    r = sweep.run_sweep("manual")
    runs.append(r["run_id"])
    reasons = query_df_strict("SELECT reason FROM agent_actions WHERE session_id = ?", [f"sweep:{r['run_id']}"])["reason"]
    assert len(reasons) == r["proposed"] and all("Approving" in x for x in reasons)


def test_sweep_endpoints_are_admin_only(login):
    assert_error(login("hcp").get("/api/actions/sweep"), 403, "forbidden")
    assert_error(login("analyst").post("/api/actions/sweep"), 403, "forbidden")
    status = assert_contract(login("admin").get("/api/actions/sweep"), SweepStatus, "sweep_status")
    assert status["schedule"].startswith("Daily at")


def test_next_run_is_today_before_and_tomorrow_after_the_slot(monkeypatch):
    monkeypatch.setattr(sweep, "SWEEP_TIME", "07:00")
    assert sweep.next_run_at(datetime(2026, 10, 10, 6, 0)).day == 10
    assert sweep.next_run_at(datetime(2026, 10, 10, 8, 0)).day == 11
