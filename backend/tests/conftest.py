"""
Shared fixtures for backend unit and contract tests.

A throwaway seed file is generated per test session so tests never depend on the developer's
.gitignored backend/seed_users.json.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

TEST_PASSWORD = "Test-Password-123"
_seed_dir = tempfile.mkdtemp(prefix="medinexus_seed_")
os.environ["MEDINEXUS_SEED_FILE"] = str(Path(_seed_dir) / "seed_users.json")
os.environ.setdefault("MEDINEXUS_JWT_SECRET", "test-secret-not-for-production")
# NEXA_LLM_PROVIDER / NEXA_SWEEP_ENABLED and the database copy are set in the project-root conftest.py

from backend.scripts.create_seed_users import build_seed  # noqa: E402

Path(os.environ["MEDINEXUS_SEED_FILE"]).write_text(json.dumps(build_seed(TEST_PASSWORD)), encoding="utf-8")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend.app.main import app  # noqa: E402

FIXTURE_DIR = PROJECT_ROOT / "frontend" / "src" / "api" / "__fixtures__"

ROLE_EMAILS = {
    "admin": "admin@medinexus.org",
    "hcp": "hcp@medinexus.org",
    "analyst": "analyst@medinexus.org",
}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def login(client):
    """login("analyst") signs the test client in with that role."""

    def _login(role: str) -> TestClient:
        r = client.post("/api/auth/login", json={"email": ROLE_EMAILS[role], "password": TEST_PASSWORD})
        assert r.status_code == 200, r.text
        return client

    return _login


def assert_contract(response, model: type[BaseModel], fixture: str, status: int = 200):
    """Response must match the Pydantic schema; the payload is saved for the frontend Vitest contract test."""
    assert response.status_code == status, response.text
    payload = response.json()
    model.model_validate(payload)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / f"{fixture}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def assert_error(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"detail", "code"} and body["code"] == code, body
    return body
