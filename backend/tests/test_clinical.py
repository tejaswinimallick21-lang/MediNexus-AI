"""
Oncology Workstation: contracts, role access, audit and care-gap logic.
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
    LabResultRow,
    LabSeries,
    MedicationRow,
    Patient360,
    PatientRisk,
    PatientSummary,
    TreatmentEvent,
    WorklistPatient,
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
def treated_patient():
    """A living patient with surgery and chemotherapy, so every Patient 360 panel has data."""
    return query_df_strict("""
        SELECT patient_id FROM gold_oncology_patients
        WHERE is_deceased = 0 AND surgeries > 0 AND chemo_cycles > 0 ORDER BY patient_id LIMIT 1
    """).iloc[0]["patient_id"]


def test_kpis_contract(hcp):
    body = assert_contract(hcp.get("/api/clinical/kpis"), ClinicalKpis, "clinical_kpis")
    assert 0 < body["in_treatment"] <= body["active_patients"]
    assert body["high_mortality_risk"] <= body["active_patients"]


def test_worklist_is_sorted_by_mortality_risk(hcp):
    body = contract_list(hcp.get("/api/clinical/worklist", params={"limit": 10}), WorklistPatient, "clinical_worklist")
    risks = [p["mortality_risk_pct"] for p in body]
    assert risks == sorted(risks, reverse=True)
    assert all(p["cancer_type"] and p["drivers"] for p in body)


def test_care_gap_contracts(hcp):
    summary = contract_list(hcp.get("/api/clinical/care-gaps/summary"), CareGapSummary, "clinical_care_gap_summary")
    assert {s["gap"] for s in summary} == {"treatment_delay", "chemo_no_cbc", "rising_marker", "follow_up_overdue", "goals_of_care"}
    assert_contract(hcp.get("/api/clinical/care-gaps", params={"limit": 5}), Page[CareGap], "clinical_care_gaps")
    assert_error(hcp.get("/api/clinical/care-gaps", params={"gap": "nope"}), 400, "unknown_gap")


def test_treatment_delay_gap_really_has_no_treatment(hcp):
    page = hcp.get("/api/clinical/care-gaps", params={"gap": "treatment_delay", "limit": 5}).json()
    assert page["items"], "the dataset has patients diagnosed more than 30 days ago without treatment"
    for gap in page["items"]:
        n = query_df_strict("""
            SELECT COUNT(*) AS n FROM gold_treatment_events
            WHERE patient_id = ? AND event_type IN ('Surgery', 'Chemotherapy', 'Immunotherapy', 'Targeted therapy', 'Radiation')
        """, [gap["patient_id"]]).iloc[0]["n"]
        assert n == 0


def test_patient_search_contract_and_filters(hcp):
    body = assert_contract(hcp.get("/api/patients", params={"search": "P_0001", "limit": 5}), Page[PatientSummary], "patients_search")
    assert all("P_0001" in p["patient_id"] for p in body["items"])
    filtered = hcp.get("/api/patients", params={"cancer_type": "Pancreas", "stage": "IV", "limit": 5}).json()["items"]
    assert filtered and all(p["cancer_type"] == "Pancreas" and p["cancer_stage"] == "IV" for p in filtered)
    assert hcp.get("/api/patients", params={"stage": "V"}).status_code == 422


def test_patient_views_contracts_and_audit(hcp, treated_patient):
    pid = treated_patient
    before = query_df_strict("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'PATIENT_VIEW' AND resource = ?", [pid]).iloc[0]["n"]
    p360 = assert_contract(hcp.get(f"/api/patients/{pid}"), Patient360, "patient_360")
    assert p360["cancer_type"] and p360["cancer_stage"] and p360["chemo_cycles"] > 0
    risk = assert_contract(hcp.get(f"/api/patients/{pid}/risk"), PatientRisk, "patient_risk")
    assert risk["available"] and 0 <= risk["mortality_12m_pct"] <= 100 and risk["care_plan"]["checklist"]
    assert risk["method"] and risk["survival_benchmark"]["patients"] > 0
    events = contract_list(hcp.get(f"/api/patients/{pid}/treatments"), TreatmentEvent, "patient_treatments")
    assert {"Surgery", "Chemotherapy"} <= {e["event_type"] for e in events}
    tests = hcp.get(f"/api/patients/{pid}/lab-tests").json()
    assert_contract(hcp.get(f"/api/patients/{pid}/labs/series", params={"test": tests[0]}), LabSeries, "patient_lab_series")
    assert_contract(hcp.get(f"/api/patients/{pid}/labs", params={"limit": 5}), Page[LabResultRow], "patient_labs")
    assert_contract(hcp.get(f"/api/patients/{pid}/medications", params={"limit": 5}), Page[MedicationRow], "patient_medications")
    stays = contract_list(hcp.get(f"/api/patients/{pid}/encounters"), EncounterRow, "patient_encounters")
    assert any(s["surgery_procedure"] for s in stays)
    after = query_df_strict("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'PATIENT_VIEW' AND resource = ?", [pid]).iloc[0]["n"]
    assert after >= before + 2  # 360 and risk views are audited


def test_deceased_patient_has_no_risk_score(hcp):
    pid = query_df_strict("SELECT patient_id FROM gold_oncology_patients WHERE is_deceased = 1 ORDER BY patient_id LIMIT 1").iloc[0]["patient_id"]
    risk = hcp.get(f"/api/patients/{pid}/risk").json()
    assert risk["available"] is False and risk["care_plan"]["pathway"] == "Closed record"


def test_unknown_and_malformed_patient(hcp):
    assert_error(hcp.get("/api/patients/P_999999"), 404, "patient_not_found")
    assert_error(hcp.get("/api/patients/DROP TABLE"), 422, "validation_error")


@pytest.mark.parametrize("role,status", [("analyst", 403), ("admin", 200), ("hcp", 200)])
def test_role_access(login, role, status):
    assert login(role).get("/api/clinical/kpis").status_code == status
    assert login(role).get("/api/patients", params={"limit": 1}).status_code == status
