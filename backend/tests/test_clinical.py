"""
Clinical Workstation: contracts, role access, audit and care-gap logic.
"""

import json
from typing import List

import pytest
from pydantic import TypeAdapter

from backend.app.core.pagination import Page
from backend.app.schemas.clinical import (
    CareGap,
    CareGapSummary,
    ClinicalKpis,
    EncounterRow,
    HuddlePatient,
    LabResultRow,
    LabSeries,
    MedicationRow,
    Patient360,
    PatientRisk,
    PatientSummary,
)
from backend.tests.conftest import FIXTURE_DIR, assert_contract, assert_error
from src.utils.database import query_df_strict


def contract_list(response, model, fixture):
    assert response.status_code == 200, response.text
    payload = response.json()
    TypeAdapter(List[model]).validate_python(payload)
    (FIXTURE_DIR / f"{fixture}.json").write_text(json.dumps(payload[:20], indent=2), encoding="utf-8")
    return payload


@pytest.fixture()
def hcp(login):
    return login("hcp")


@pytest.fixture()
def huddle_patient(hcp):
    return hcp.get("/api/clinical/huddle", params={"limit": 1}).json()[0]["patient_id"]


def test_kpis_contract(hcp):
    body = assert_contract(hcp.get("/api/clinical/kpis"), ClinicalKpis, "clinical_kpis")
    assert body["high_risk_recent_discharges"] <= body["recent_discharges"]


def test_huddle_is_sorted_by_risk(hcp):
    body = contract_list(hcp.get("/api/clinical/huddle", params={"limit": 10}), HuddlePatient, "clinical_huddle")
    probs = [p["readmission_probability_pct"] for p in body]
    assert probs == sorted(probs, reverse=True)


def test_care_gap_contracts(hcp):
    summary = contract_list(hcp.get("/api/clinical/care-gaps/summary"), CareGapSummary, "clinical_care_gap_summary")
    assert {s["gap"] for s in summary} >= {"diabetes_hba1c", "high_risk_no_follow_up"}
    assert_contract(hcp.get("/api/clinical/care-gaps", params={"limit": 5}), Page[CareGap], "clinical_care_gaps")
    assert_error(hcp.get("/api/clinical/care-gaps", params={"gap": "nope"}), 400, "unknown_gap")


def test_diabetes_gap_really_lacks_recent_hba1c(hcp):
    page = hcp.get("/api/clinical/care-gaps", params={"gap": "diabetes_hba1c", "limit": 3}).json()
    end = query_df_strict("SELECT max(test_date) AS d FROM gold_laboratory").iloc[0]["d"]
    for gap in page["items"]:
        recent = query_df_strict(
            "SELECT COUNT(*) AS n FROM gold_laboratory WHERE patient_id = ? AND test_name = 'HbA1c' AND CAST(test_date AS DATE) > CAST(? AS DATE) - INTERVAL 365 DAY",
            [gap["patient_id"], end],
        ).iloc[0]["n"]
        assert recent == 0


def test_patient_search_contract(hcp):
    body = assert_contract(hcp.get("/api/patients", params={"search": "P_0001", "limit": 5}), Page[PatientSummary], "patients_search")
    assert all("P_0001" in p["patient_id"] for p in body["items"])


def test_patient_views_contracts_and_audit(hcp, huddle_patient):
    pid = huddle_patient
    before = query_df_strict("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'PATIENT_VIEW' AND resource = ?", [pid]).iloc[0]["n"]
    assert_contract(hcp.get(f"/api/patients/{pid}"), Patient360, "patient_360")
    risk = assert_contract(hcp.get(f"/api/patients/{pid}/risk"), PatientRisk, "patient_risk")
    assert risk["readmission_available"] and risk["care_plan"]["checklist"]
    tests = hcp.get(f"/api/patients/{pid}/lab-tests").json()
    assert_contract(hcp.get(f"/api/patients/{pid}/labs/series", params={"test": tests[0]}), LabSeries, "patient_lab_series")
    assert_contract(hcp.get(f"/api/patients/{pid}/labs", params={"limit": 5}), Page[LabResultRow], "patient_labs")
    assert_contract(hcp.get(f"/api/patients/{pid}/medications", params={"limit": 5}), Page[MedicationRow], "patient_medications")
    contract_list(hcp.get(f"/api/patients/{pid}/encounters"), EncounterRow, "patient_encounters")
    after = query_df_strict("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'PATIENT_VIEW' AND resource = ?", [pid]).iloc[0]["n"]
    assert after >= before + 2  # 360 and risk views are audited


def test_unknown_and_malformed_patient(hcp):
    assert_error(hcp.get("/api/patients/P_999999"), 404, "patient_not_found")
    assert_error(hcp.get("/api/patients/DROP TABLE"), 422, "validation_error")


@pytest.mark.parametrize("role,status", [("analyst", 403), ("admin", 200), ("hcp", 200)])
def test_role_access(login, role, status):
    assert login(role).get("/api/clinical/kpis").status_code == status
    assert login(role).get("/api/patients", params={"limit": 1}).status_code == status
