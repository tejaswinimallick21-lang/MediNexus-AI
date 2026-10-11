"""
One account per person: admins add people (temporary password, forced change at first sign-in),
change roles, disable and reset; safety rules; sessions end on disable and password change.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.users import clear_cache
from backend.app.main import app
from backend.app.schemas.auth import UserOut
from backend.app.schemas.users import TemporaryPassword, UserAdminRow, UserDirectory
from backend.tests.conftest import TEST_PASSWORD, assert_contract, assert_error
from src.utils.database import execute_query, query_df_strict

NEW = "dr.rivera@medinexus.org"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    execute_query("DELETE FROM app_users WHERE email LIKE '%@medinexus.org' AND created_by <> 'seed file'")
    execute_query("UPDATE app_users SET active = TRUE, role = 'analyst' WHERE email = 'analyst@medinexus.org'")
    clear_cache()


def _add(admin, email=NEW, role="hcp"):
    return admin.post("/api/users", json={"email": email, "name": "Dr Ana Rivera", "role": role, "department": "Cardiology"})


def test_admin_adds_a_person_who_must_change_the_temporary_password(login):
    admin = login("admin")
    created = assert_contract(_add(admin), TemporaryPassword, "user_created", status=201)
    temp = created["temporary_password"]
    assert len(temp) >= 12 and created["user"]["must_change_password"] and created["user"]["created_by"] == "admin@medinexus.org"
    assert_contract(admin.get("/api/users"), UserDirectory, "user_directory")

    with TestClient(app) as person:
        me = person.post("/api/auth/login", json={"email": NEW, "password": temp}).json()
        assert me["must_change_password"] and me["role"] == "hcp"
        assert_error(person.get("/api/clinical/kpis"), 403, "password_change_required")  # blocked until changed
        assert_error(person.post("/api/auth/password", json={"current_password": temp, "new_password": "short1"}), 422, "weak_password")
        assert_error(person.post("/api/auth/password", json={"current_password": "wrong", "new_password": "Cardio-2026-ok"}), 400, "wrong_password")
        done = assert_contract(person.post("/api/auth/password", json={"current_password": temp, "new_password": "Cardio-2026-ok"}), UserOut, "auth_password_changed")
        assert done["must_change_password"] is False
        assert person.get("/api/clinical/kpis").status_code == 200  # fresh session cookie still works

    audit = query_df_strict("SELECT action, details FROM audit_logs WHERE resource = ? OR username = ?", [f"USER:{NEW}", NEW])
    assert {"USER_CREATE", "LOGIN", "PASSWORD_CHANGE"} <= set(audit["action"])
    assert not audit["details"].str.contains("Cardio-2026-ok|" + temp).any()  # passwords never audited


def test_disabling_ends_the_session_and_blocks_sign_in(login):
    admin = login("admin")
    temp = _add(admin).json()["temporary_password"]
    with TestClient(app) as person:
        person.post("/api/auth/login", json={"email": NEW, "password": temp})
        person.post("/api/auth/password", json={"current_password": temp, "new_password": "Cardio-2026-ok"})
        assert person.get("/api/auth/me").status_code == 200
        row = admin.patch(f"/api/users/{NEW}", json={"active": False}).json()
        assert row["active"] is False
        assert_error(person.get("/api/auth/me"), 401, "not_authenticated")
        assert_error(person.post("/api/auth/login", json={"email": NEW, "password": "Cardio-2026-ok"}), 401, "invalid_credentials")
    assert admin.patch(f"/api/users/{NEW}", json={"active": True}).json()["active"] is True


def test_reset_ends_sessions_and_forces_a_new_password(login):
    admin = login("admin")
    temp = _add(admin).json()["temporary_password"]
    with TestClient(app) as person:
        person.post("/api/auth/login", json={"email": NEW, "password": temp})
        person.post("/api/auth/password", json={"current_password": temp, "new_password": "Cardio-2026-ok"})
        reset = admin.post(f"/api/users/{NEW}/reset-password").json()
        assert reset["temporary_password"] != temp and reset["user"]["must_change_password"]
        assert_error(person.get("/api/auth/me"), 401, "not_authenticated")
        assert person.post("/api/auth/login", json={"email": NEW, "password": reset["temporary_password"]}).json()["must_change_password"]


def test_role_change_takes_effect_immediately(login):
    admin = login("admin")
    temp = _add(admin, role="analyst").json()["temporary_password"]
    with TestClient(app) as person:
        person.post("/api/auth/login", json={"email": NEW, "password": temp})
        person.post("/api/auth/password", json={"current_password": temp, "new_password": "Cardio-2026-ok"})
        assert person.get("/api/clinical/kpis").status_code == 403
        assert_contract(admin.patch(f"/api/users/{NEW}", json={"role": "hcp"}), UserAdminRow, "user_updated")
        assert person.get("/api/clinical/kpis").status_code == 200


def test_safety_rules(login):
    admin = login("admin")
    assert_error(admin.patch("/api/users/admin@medinexus.org", json={"active": False}), 409, "cannot_modify_self")
    assert_error(admin.patch("/api/users/admin@medinexus.org", json={"role": "hcp"}), 409, "cannot_modify_self")
    assert_error(admin.post("/api/users/admin@medinexus.org/reset-password"), 409, "cannot_modify_self")
    assert_error(_add(admin, email="admin@medinexus.org"), 409, "user_exists")
    assert_error(admin.patch("/api/users/nobody@medinexus.org", json={"active": False}), 404, "user_not_found")
    # A second admin can be demoted, but never the last active one
    _add(admin, role="admin")
    assert admin.patch(f"/api/users/{NEW}", json={"role": "analyst"}).json()["role"] == "analyst"
    with TestClient(app) as other:  # the only remaining admin cannot be removed by anyone
        assert admin.patch("/api/users/analyst@medinexus.org", json={"role": "admin"}).status_code == 200
        other.post("/api/auth/login", json={"email": "analyst@medinexus.org", "password": TEST_PASSWORD})
        assert other.patch("/api/users/admin@medinexus.org", json={"role": "hcp"}).status_code == 200
        assert_error(other.patch("/api/users/analyst@medinexus.org", json={"role": "hcp"}), 409, "cannot_modify_self")
    execute_query("UPDATE app_users SET role = 'admin' WHERE email = 'admin@medinexus.org'")
    clear_cache()


def test_only_admins_manage_people(login):
    assert_error(login("hcp").get("/api/users"), 403, "forbidden")
    assert_error(login("analyst").post("/api/users", json={"email": NEW, "name": "X", "role": "hcp"}), 403, "forbidden")
