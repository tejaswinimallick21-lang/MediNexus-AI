"""Oncology Workstation routes (/api/clinical/*, /api/patients/*): hcp role, admins oversee."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query

from backend.app.core.deps import require_page
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.core.users import UserRecord
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
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.services import clinical

guard = require_page("doctor")
PatientId = Path(..., pattern=r"^P_\d{1,6}$")

clinical_router = APIRouter(prefix="/clinical", tags=["clinical"], responses=ERROR_RESPONSES, dependencies=[Depends(guard)])
patients_router = APIRouter(prefix="/patients", tags=["patients"], responses=ERROR_RESPONSES)


@clinical_router.get("/kpis", response_model=ClinicalKpis)
def kpis() -> ClinicalKpis:
    return clinical.get_kpis()


@clinical_router.get("/worklist", response_model=List[WorklistPatient])
def worklist(limit: int = Query(20, ge=1, le=100)) -> List[WorklistPatient]:
    """Tumour-board worklist: living cancer patients ranked by 12-month mortality risk."""
    return clinical.get_worklist(limit)


@clinical_router.get("/care-gaps/summary", response_model=List[CareGapSummary])
def care_gap_summary() -> List[CareGapSummary]:
    return clinical.get_care_gap_summary()


@clinical_router.get("/care-gaps", response_model=Page[CareGap])
def care_gaps(params: PageParams = Depends(page_params), gap: Optional[str] = Query(None, max_length=40)) -> Page[CareGap]:
    return clinical.list_care_gaps(params, gap)


@patients_router.get("", response_model=Page[PatientSummary])
def search(
    params: PageParams = Depends(page_params),
    search: Optional[str] = Query(None, max_length=80),
    tier: Optional[str] = Query(None, pattern="^(High|Moderate|Low)$"),
    cancer_type: Optional[str] = Query(None, max_length=40),
    stage: Optional[str] = Query(None, pattern="^(I|II|III|IV)$"),
    _: UserRecord = Depends(guard),
) -> Page[PatientSummary]:
    return clinical.search_patients(params, search, tier, cancer_type, stage)


@patients_router.get("/{patient_id}", response_model=Patient360)
def patient_360(patient_id: str = PatientId, user: UserRecord = Depends(guard)) -> Patient360:
    return clinical.get_patient_360(patient_id, user)


@patients_router.get("/{patient_id}/risk", response_model=PatientRisk)
def patient_risk(patient_id: str = PatientId, user: UserRecord = Depends(guard)) -> PatientRisk:
    return clinical.get_patient_risk(patient_id, user)


@patients_router.get("/{patient_id}/treatments", response_model=List[TreatmentEvent])
def treatments(patient_id: str = PatientId, _: UserRecord = Depends(guard)) -> List[TreatmentEvent]:
    return clinical.get_treatments(patient_id)


@patients_router.get("/{patient_id}/lab-tests", response_model=List[str])
def lab_tests(patient_id: str = PatientId, _: UserRecord = Depends(guard)) -> List[str]:
    return clinical.get_lab_tests(patient_id)


@patients_router.get("/{patient_id}/labs/series", response_model=LabSeries)
def lab_series(patient_id: str = PatientId, test: str = Query(..., max_length=80), _: UserRecord = Depends(guard)) -> LabSeries:
    return clinical.get_lab_series(patient_id, test)


@patients_router.get("/{patient_id}/labs", response_model=Page[LabResultRow])
def labs(patient_id: str = PatientId, params: PageParams = Depends(page_params), _: UserRecord = Depends(guard)) -> Page[LabResultRow]:
    return clinical.get_recent_labs(patient_id, params)


@patients_router.get("/{patient_id}/medications", response_model=Page[MedicationRow])
def medications(patient_id: str = PatientId, params: PageParams = Depends(page_params), _: UserRecord = Depends(guard)) -> Page[MedicationRow]:
    return clinical.get_medications(patient_id, params)


@patients_router.get("/{patient_id}/encounters", response_model=List[EncounterRow])
def encounters(patient_id: str = PatientId, _: UserRecord = Depends(guard)) -> List[EncounterRow]:
    return clinical.get_encounters(patient_id)
