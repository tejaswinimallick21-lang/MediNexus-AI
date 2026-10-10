"""
Security & Infrastructure workspace, login lockout, security headers and knowledge-library management.
Embeddings use the local model in tests (no API calls); uploads and benchmark output go to temp folders.
"""

import io

import pytest

from backend.app.core.pagination import Page
from backend.app.schemas.security import AccessMatrix, AiGovernance, AuditEvent, AuditSummary, InfraHealth, KnowledgeLibrary, Posture, SearchComparison
from backend.app.services import auth as auth_service
from backend.tests.conftest import assert_contract, assert_error
from src.rag import benchmark, hybrid


@pytest.fixture()
def temp_knowledge(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid, "UPLOADED_DIR", tmp_path / "knowledge")
    monkeypatch.setattr("backend.app.services.knowledge.UPLOADED_DIR", tmp_path / "knowledge")
    monkeypatch.setattr(benchmark, "RESULTS_PATH", tmp_path / "bench.json")
    yield tmp_path


def test_workspace_is_admin_only(login, client):
    assert_error(client.get("/api/security/posture"), 401, "not_authenticated")
    assert_error(login("hcp").get("/api/security/posture"), 403, "forbidden")
    assert_error(login("analyst").get("/api/knowledge/documents"), 403, "forbidden")


def test_posture_reports_live_checks(login):
    body = assert_contract(login("admin").get("/api/security/posture"), Posture, "security_posture")
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["login_lockout"]["status"] == "pass"
    assert checks["secrets_git"]["status"] in ("pass", "warn")  # never "fail": no keys are committed
    assert body["passed"] + body["warnings"] + body["failures"] == len(body["checks"])


def test_audit_trail_and_summary(login):
    c = login("admin")
    page = assert_contract(c.get("/api/security/audit", params={"limit": 5, "action": "LOGIN"}), Page[AuditEvent], "security_audit")
    assert page["items"] and all(e["action"] == "LOGIN" for e in page["items"])
    s = assert_contract(c.get("/api/security/audit/summary", params={"days": 7}), AuditSummary, "security_audit_summary")
    assert s["total_events"] > 0 and "LOGIN" in s["actions"]


def test_access_infra_and_ai_contracts(login):
    c = login("admin")
    m = assert_contract(c.get("/api/security/access"), AccessMatrix, "security_access")
    it = next(w for w in m["workspaces"] if w["route"] == "/it")
    assert it["roles"] == ["admin"]
    infra = assert_contract(c.get("/api/security/infra"), InfraHealth, "security_infra")
    assert infra["database_size_mb"] > 0 and infra["layer_rows"]["gold"] > 0
    ai = assert_contract(c.get("/api/security/ai"), AiGovernance, "security_ai")
    assert ai["guardrails"] and ai["caps"]["max_tool_rounds"] >= 1


def test_security_headers_on_responses(client):
    r = client.get("/api/system/status")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_login_lockout_after_repeated_failures(client):
    email = "intruder@example.com"
    try:
        for _ in range(auth_service.MAX_FAILURES):
            assert_error(client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}), 401, "invalid_credentials")
        assert_error(client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}), 429, "account_locked")
    finally:
        auth_service._locked_until.pop(email, None)
        auth_service._failures.pop(email, None)


def test_knowledge_upload_search_delete(login, temp_knowledge):
    c = login("admin")
    lib = assert_contract(c.get("/api/knowledge/documents"), KnowledgeLibrary, "knowledge_library")
    assert len(lib["documents"]) >= 20

    doc = ("DOCUMENT TITLE: Visitor Hours Policy\nDOCUMENT ID: POL-OPS-099\n\n1. GENERAL WARDS\nVisitors are welcome between 10:00 and 20:00. "
           "A maximum of two visitors per patient at the bedside at any time. Children under 12 must be accompanied by an adult.\n")
    r = c.post("/api/knowledge/documents", files={"file": ("visitor_hours.md", io.BytesIO(doc.encode()), "text/markdown")})
    assert r.status_code == 201, r.text
    assert any(d["doc_id"] == "visitor_hours" and d["source"] == "uploaded" for d in r.json()["documents"])

    found = assert_contract(c.post("/api/knowledge/search", json={"query": "POL-OPS-099 visitors"}), SearchComparison, "knowledge_search")
    assert found["identifier_query"] and found["results"]["hybrid"][0]["policy_id"] == "POL-OPS-099"

    assert c.delete("/api/knowledge/documents/visitor_hours").status_code == 204
    assert_error(c.delete("/api/knowledge/documents/hand_hygiene_policy"), 404, "document_not_found")  # library docs are protected
    assert_error(c.post("/api/knowledge/documents", files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")}), 422, "unsupported_file")


def test_benchmark_compares_three_modes(login, temp_knowledge):
    from backend.tests.conftest import FIXTURE_DIR
    import json

    r = login("admin").post("/api/knowledge/benchmark")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["mode"] for m in body["modes"]] == ["bm25", "dense", "hybrid"]
    hybrid_row = body["modes"][2]["summary"]
    assert hybrid_row["keyword"]["hit1_pct"] >= 80 and hybrid_row["exact"]["hit1_pct"] >= 80
    slim = {**body, "modes": [{**m, "rows": m["rows"][:2]} for m in body["modes"]]}
    (FIXTURE_DIR / "knowledge_benchmark.json").write_text(json.dumps(slim, indent=1), encoding="utf-8")
