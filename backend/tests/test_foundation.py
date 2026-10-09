"""
Contract + unit tests for auth, system metadata, access policy, pagination and jobs.
"""

import time

import pytest

from backend.app.core.access import allowed_routes, can_access
from backend.app.core.errors import APIError
from backend.app.core.pagination import PageParams, build_page, decode_cursor, encode_cursor
from backend.app.jobs import runner
from backend.app.schemas.auth import UserOut
from backend.app.schemas.common import ErrorOut
from backend.app.schemas.system import PlatformOverview, SystemStatus
from backend.tests.conftest import PERSONA_EMAILS, TEST_PASSWORD, assert_contract, assert_error


# ---- contracts -------------------------------------------------------------------------------

def test_login_contract_and_cookie(client):
    r = client.post("/api/auth/login", json={"email": PERSONA_EMAILS["Receptionist"], "password": TEST_PASSWORD})
    body = assert_contract(r, UserOut, "auth_me")
    assert body["role"] == "hcp" and body["persona"] == "Receptionist"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_me_requires_session(client):
    assert_error(client.get("/api/auth/me"), 401, "not_authenticated")


def test_me_after_login(login):
    c = login("Doctor")
    assert UserOut.model_validate(c.get("/api/auth/me").json()).allowed_routes == ["/doctor"]


def test_bad_credentials(client):
    body = assert_error(
        client.post("/api/auth/login", json={"email": PERSONA_EMAILS["Doctor"], "password": "wrong"}), 401, "invalid_credentials"
    )
    ErrorOut.model_validate(body)


def test_invalid_email_is_validation_error(client):
    assert_error(client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"}), 422, "validation_error")


def test_logout_clears_session(login):
    c = login("Pharmacist")
    assert c.post("/api/auth/logout").status_code == 204
    assert_error(c.get("/api/auth/me"), 401, "not_authenticated")


def test_tampered_cookie_rejected(client):
    client.cookies.set("medinexus_session", "not-a-jwt")
    assert_error(client.get("/api/auth/me"), 401, "not_authenticated")


def test_system_status_contract(client):
    assert_contract(client.get("/api/system/status"), SystemStatus, "system_status")


def test_platform_overview_contract(client):
    body = assert_contract(client.get("/api/platform/overview"), PlatformOverview, "platform_overview")
    assert len(body["personas"]) == 7


def test_unknown_job_is_404(login):
    assert_error(login("Doctor").get("/api/jobs/does-not-exist"), 404, "job_not_found")


# ---- access policy ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,persona,page,expected", [
    ("hcp", "Receptionist", "reception", True),
    ("hcp", "Receptionist", "doctor", False),       # privacy: no clinical pages for the front desk
    ("hcp", "Doctor", "doctor", True),
    ("analyst", "Hospital Administrator", "executive", True),
    ("admin", "Data Engineer", "data", True),
    ("admin", "IT Administrator", "it", True),
    ("hcp", "Data Engineer", "data", False),        # persona/role mismatch is always denied
])
def test_can_access(role, persona, page, expected):
    assert can_access(role, persona, page) is expected


def test_allowed_routes_match_streamlit_rbac():
    assert allowed_routes("admin", "Data Engineer") == ["/it", "/data"]
    assert allowed_routes("hcp", "Laboratory Technician") == ["/laboratory"]


# ---- pagination ------------------------------------------------------------------------------

def test_cursor_round_trip():
    assert decode_cursor(encode_cursor(150)) == 150
    assert decode_cursor(None) == 0


def test_invalid_cursor():
    with pytest.raises(APIError) as exc:
        decode_cursor("@@@")
    assert exc.value.code == "invalid_cursor"


def test_build_page_sets_next_cursor_only_when_more_rows():
    params = PageParams(limit=2, offset=0)
    assert build_page([1, 2, 3], params).next_cursor == encode_cursor(2)
    assert build_page([1, 2], params).next_cursor is None


# ---- jobs ------------------------------------------------------------------------------------

def test_job_runner_reports_progress_and_result():
    def work(ctx):
        ctx.progress(50, "Halfway")
        return {"answer": 42}

    job = runner.submit("unit-test", "tester@medinexus.org", work)
    for _ in range(100):
        if job.to_out().status in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    out = job.to_out()
    assert out.status == "succeeded" and out.result == {"answer": 42} and out.progress_pct == 100
    assert any("Halfway" in line for line in out.logs)


def test_job_runner_captures_failure():
    job = runner.submit("unit-test", "tester@medinexus.org", lambda ctx: 1 / 0)
    for _ in range(100):
        if job.to_out().status in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job.to_out().status == "failed" and "division by zero" in job.to_out().error
