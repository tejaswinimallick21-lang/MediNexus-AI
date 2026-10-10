"""
Long-term memory: explicit saves (chat and panel), patient-data refusal, per-user isolation,
prompt injection as preferences, and deletion. Runs on the isolated test database copy.
"""

import pytest

from backend.app.agents import engine, memory
from backend.app.core.users import UserRecord
from backend.app.schemas.assistant import MemoryItem
from backend.tests.conftest import assert_contract, assert_error
from backend.tests.test_operations import contract_list
from src.utils.database import execute_query, query_df_strict


@pytest.fixture(autouse=True)
def clean():
    memory._ensure()
    execute_query("DELETE FROM agent_memory")
    yield
    execute_query("DELETE FROM agent_memory")


def test_panel_save_list_delete(login):
    c = login("analyst")
    saved = assert_contract(c.post("/api/assistant/memory", json={"text": "I review Site North every Monday"}), MemoryItem, "memory_item", status=201)
    assert saved["source"] == "panel"
    again = c.post("/api/assistant/memory", json={"text": "i review site north every monday"}).json()
    assert again["memory_id"] == saved["memory_id"]  # no duplicates
    rows = contract_list(c.get("/api/assistant/memory"), MemoryItem, "memory_list")
    assert [r["text"] for r in rows] == ["I review Site North every Monday"]
    assert c.delete(f"/api/assistant/memory/{saved['memory_id']}").status_code == 204
    assert c.get("/api/assistant/memory").json() == []


@pytest.mark.parametrize("text", ["Patient P_04436 is my priority", "Call me on +1 555 201 3344", "My email is a.b@example.org", "Her date of birth is in May"])
def test_patient_and_personal_data_is_refused(login, text):
    assert_error(login("hcp").post("/api/assistant/memory", json={"text": text}), 422, "memory_has_identifiers")


def test_memories_are_private_to_each_user(login):
    m = login("analyst").post("/api/assistant/memory", json={"text": "Show money in thousands"}).json()
    hcp = login("hcp")
    assert hcp.get("/api/assistant/memory").json() == []
    assert_error(hcp.delete(f"/api/assistant/memory/{m['memory_id']}"), 404, "memory_not_found")


def test_remember_in_chat_saves_and_is_audited_without_text(login):
    c = login("analyst")
    sid = c.post("/api/assistant/sessions", json={"agent": "healthanalyst"}).json()["session_id"]
    try:
        reply = c.post(f"/api/assistant/sessions/{sid}/messages", json={"message": "Remember that I focus on emergency admissions"}).json()["messages"][1]["reply"]
        assert reply["tool_calls"][0]["name"] == "remember" and reply["tool_calls"][0]["ok"]
        assert [m["source"] for m in c.get("/api/assistant/memory").json()] == ["chat"]
        refused = c.post(f"/api/assistant/sessions/{sid}/messages", json={"message": "Remember P_00012 needs a call"}).json()["messages"][1]["reply"]
        assert "patient ID" in refused["answer"] and len(c.get("/api/assistant/memory").json()) == 1
        audit = query_df_strict("SELECT details FROM audit_logs WHERE action = 'MEMORY_SAVE' ORDER BY timestamp DESC LIMIT 1")
        assert "emergency" not in str(audit.iloc[0, 0]).lower()
    finally:
        execute_query("DELETE FROM assistant_messages WHERE session_id = ?", [sid])
        execute_query("DELETE FROM assistant_sessions WHERE session_id = ?", [sid])


def test_memories_reach_the_prompt_as_preferences_not_data():
    user = UserRecord(email="pref@test.org", name="Pref Test", role="analyst", department="Analytics", password_hash="")
    assert engine.system_prompt("healthanalyst", memory.prompt_block(user)) == engine.system_prompt("healthanalyst")
    memory.add(user, "remember to show rates with one decimal")
    block = memory.prompt_block(user)
    assert "Show rates with one decimal" in block and "NOT data" in block
    assert block in engine.system_prompt("healthanalyst", block)
    assert memory.clear(user) == 1 and memory.prompt_block(user) == ""
