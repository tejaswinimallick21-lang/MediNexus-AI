"""
Nexa agents: grounding (rules engine), tool scoping by role, proposal → approval → execution,
and fallback when the LLM is unavailable. No paid LLM is called: a fake provider drives the tools.
"""

import pytest

from backend.app.agents import providers
from backend.app.schemas.actions import ActionInbox, AgentAction
from backend.app.schemas.operations import AgentReply
from backend.tests.conftest import assert_contract, assert_error
from src.utils.database import execute_query, query_df_strict


@pytest.fixture()
def cleanup():
    ids = []
    yield ids
    for a in ids:
        execute_query("DELETE FROM care_tasks WHERE source_action_id = ?", [a])
        execute_query("DELETE FROM purchase_orders WHERE po_id IN (SELECT regexp_extract(result, 'PO_[0-9A-F]+') FROM agent_actions WHERE action_id = ?)", [a])
        execute_query("DELETE FROM agent_actions WHERE action_id = ?", [a])


def fake_llm(script):
    """A provider that calls the scripted tools, then answers with a fixed sentence."""

    def run(system, history, message, tools, execute):
        trace = []
        for name, args in script:
            r = execute(name, args)
            trace.append({"name": name, "args": args, "ok": bool(r.get("ok")), "error": r.get("error")})
        return "Answer from tools.", trace

    return run


def chat(c, agent, message):
    r = c.post(f"/api/agents/{agent}/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return AgentReply.model_validate(r.json())


# ---- rules engine: grounded or refuses ------------------------------------------------------------

def test_out_of_scope_question_is_refused_not_answered(login):
    reply = chat(login("hcp"), "medicare", "What is the weather today?")
    assert reply.answer.startswith("I can't answer that") and not reply.facts and not reply.tool_calls


def test_mortality_by_stage_uses_the_right_tool(login):
    reply = chat(login("analyst"), "healthanalyst", "Which cancer stage has the highest mortality?")
    assert [t.name for t in reply.tool_calls] == ["get_outcomes_by"]
    assert reply.tool_calls[0].args == {"dimension": "stage"}
    assert reply.facts and "died pct" in reply.facts[0] and "Stage IV" in reply.facts[0]


def test_agent_outputs_never_contain_patient_names(login):
    reply = chat(login("hcp"), "medicare", "Show me the highest-risk patients")
    names = query_df_strict("SELECT DISTINCT name FROM gold_patient_360 WHERE name IS NOT NULL LIMIT 500")["name"]
    text = " ".join(reply.facts + [reply.answer or ""])
    assert reply.facts and "P_" in text
    assert not any(n in text for n in names if len(str(n)) > 4)


def test_unknown_medicine_reports_no_records(login):
    reply = chat(login("hcp"), "pharmalab", "How many units of unobtainium do we have?")
    assert reply.facts == ["No matching records."]


# ---- tool scoping and actions ---------------------------------------------------------------------

def test_tools_are_scoped_to_agent_and_role(login, monkeypatch):
    monkeypatch.setattr(providers, "active_provider", lambda: "openai")
    monkeypatch.setattr(providers, "run_openai", fake_llm([("get_patient_summary", {"patient_id": "P_04436"})]))
    reply = chat(login("analyst"), "healthanalyst", "Tell me about P_04436")
    assert reply.tool_calls[0].ok is False and "not available" in reply.tool_calls[0].error


def test_proposal_requires_approval_then_executes(login, monkeypatch, cleanup):
    line = query_df_strict("SELECT inventory_id FROM gold_pharmacy LIMIT 1").iloc[0]["inventory_id"]
    monkeypatch.setattr(providers, "active_provider", lambda: "openai")
    monkeypatch.setattr(providers, "run_openai", fake_llm([("propose_purchase_order", {"inventory_id": line, "quantity": 12, "reason": "test"})]))
    c = login("hcp")
    reply = chat(c, "pharmalab", "Order more of this")
    assert len(reply.proposed_actions) == 1 and reply.proposed_actions[0].status == "pending"
    action_id = reply.proposed_actions[0].action_id
    cleanup.append(action_id)

    assert query_df_strict("SELECT COUNT(*) AS n FROM purchase_orders WHERE inventory_id = ? AND quantity = 12 AND created_at > now() - INTERVAL 1 MINUTE",
                           [line]).iloc[0]["n"] == 0  # nothing ordered yet

    assert_error(login("analyst").post(f"/api/actions/{action_id}/approve", json={}), 403, "forbidden")
    c = login("hcp")
    inbox = assert_contract(c.get("/api/actions", params={"status": "pending"}), ActionInbox, "actions_inbox")
    assert inbox["pending"] >= 1 and any(a["action_id"] == action_id and a["can_decide"] for a in inbox["items"])

    done = assert_contract(c.post(f"/api/actions/{action_id}/approve", json={"note": "ok"}), AgentAction, "action_decided")
    assert done["status"] == "executed" and done["result"].startswith("Purchase order PO_")
    assert_error(c.post(f"/api/actions/{action_id}/reject", json={}), 409, "already_decided")


def test_follow_up_rejection_creates_nothing(login, monkeypatch, cleanup):
    monkeypatch.setattr(providers, "active_provider", lambda: "openai")
    monkeypatch.setattr(providers, "run_openai", fake_llm([("propose_follow_up", {"patient_id": "P_04436", "reason": "high risk", "due_in_days": 7})]))
    c = login("hcp")
    action_id = chat(c, "medicare", "Book a follow-up").proposed_actions[0].action_id
    cleanup.append(action_id)
    r = c.post(f"/api/actions/{action_id}/reject", json={"note": "already booked"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert query_df_strict("SELECT COUNT(*) AS n FROM care_tasks WHERE source_action_id = ?", [action_id]).iloc[0]["n"] == 0


def test_llm_failure_falls_back_to_rules(login, monkeypatch):
    def broken(*a, **k):
        raise providers.ProviderError("The OpenAI API key was rejected.")

    monkeypatch.setattr(providers, "active_provider", lambda: "openai")
    monkeypatch.setattr(providers, "run_openai", broken)
    reply = chat(login("analyst"), "healthanalyst", "Which stage has the highest mortality?")
    assert reply.engine == "Rules engine (fallback)" and "key was rejected" in reply.notes and reply.facts


def test_ops_agent_is_admin_only(login):
    assert_error(login("analyst").post("/api/agents/ops/chat", json={"message": "hi"}), 403, "forbidden")
    assert chat(login("admin"), "ops", "Which cancer type has the lowest survival?").tool_calls
