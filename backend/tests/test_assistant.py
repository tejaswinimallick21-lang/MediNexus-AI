"""
Nexa assistant: agent catalogue per role and persisted conversation sessions.
"""

import pytest

from backend.app.core.pagination import Page
from backend.app.schemas.assistant import AssistantAgent, AssistantExchange, AssistantMessage, AssistantSession
from backend.tests.conftest import assert_contract, assert_error
from backend.tests.test_operations import contract_list
from src.utils.database import execute_query


@pytest.fixture()
def created(request):
    """Collects session ids created by a test and removes them afterwards (dev DB stays clean)."""
    ids = []
    yield ids
    for sid in ids:
        execute_query("DELETE FROM assistant_messages WHERE session_id = ?", [sid])
        execute_query("DELETE FROM assistant_sessions WHERE session_id = ?", [sid])


def test_agent_catalogue_follows_role(login):
    rows = contract_list(login("hcp").get("/api/assistant/agents"), AssistantAgent, "assistant_agents")
    assert {r["key"] for r in rows} == {"medicare", "pharmalab"}


def test_analyst_cannot_open_clinical_assistant(login):
    assert_error(login("analyst").post("/api/assistant/sessions", json={"agent": "medicare"}), 403, "forbidden")


def test_session_lifecycle(login, created):
    c = login("analyst")
    session = assert_contract(c.post("/api/assistant/sessions", json={"agent": "healthanalyst"}), AssistantSession, "assistant_session", status=201)
    created.append(session["session_id"])
    assert session["title"] == "New conversation" and session["message_count"] == 0

    exchange = assert_contract(
        c.post(f"/api/assistant/sessions/{session['session_id']}/messages", json={"message": "Provide bed capacity and surge forecast"}),
        AssistantExchange, "assistant_exchange",
    )
    assert exchange["session"]["title"] == "Provide bed capacity and surge forecast"
    assert exchange["session"]["message_count"] == 2
    assert [m["role"] for m in exchange["messages"]] == ["user", "assistant"]

    history = c.get(f"/api/assistant/sessions/{session['session_id']}/messages")
    assert history.status_code == 200
    msgs = [AssistantMessage.model_validate(m) for m in history.json()]
    assert [m.role for m in msgs] == ["user", "assistant"] and msgs[1].reply is not None
    from backend.tests.conftest import FIXTURE_DIR
    (FIXTURE_DIR / "assistant_messages.json").write_text(history.text, encoding="utf-8")

    listed = assert_contract(c.get("/api/assistant/sessions", params={"limit": 100}), Page[AssistantSession], "assistant_sessions")
    assert listed["items"][0]["session_id"] == session["session_id"]  # most recently updated first

    renamed = c.patch(f"/api/assistant/sessions/{session['session_id']}", json={"title": "Capacity review"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "Capacity review"

    assert c.delete(f"/api/assistant/sessions/{session['session_id']}").status_code == 204
    assert_error(c.get(f"/api/assistant/sessions/{session['session_id']}/messages"), 404, "session_not_found")


def test_sessions_are_private(login, created):
    c = login("admin")
    sid = c.post("/api/assistant/sessions", json={"agent": "healthanalyst"}).json()["session_id"]
    created.append(sid)
    c = login("analyst")
    assert_error(c.get(f"/api/assistant/sessions/{sid}/messages"), 404, "session_not_found")
    assert_error(c.delete(f"/api/assistant/sessions/{sid}"), 404, "session_not_found")


def test_empty_message_is_not_stored(login, created):
    c = login("hcp")
    sid = c.post("/api/assistant/sessions", json={"agent": "medicare"}).json()["session_id"]
    created.append(sid)
    assert_error(c.post(f"/api/assistant/sessions/{sid}/messages", json={"message": "   "}), 422, "empty_message")
    assert c.get(f"/api/assistant/sessions/{sid}/messages").json() == []
