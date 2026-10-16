"""Schemas for the Oncology Workstation (Clinical workspace)."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class ClinicalKpis(BaseModel):
    active_patients: int          # living patients with a cancer diagnosis
    in_treatment: int             # a treatment session in the last 30 days
    awaiting_treatment: int       # diagnosed in the last 90 days, no treatment yet
    high_mortality_risk: int      # 12-month mortality risk in the top band
    open_care_gaps: int
    data_through: str


class WorklistPatient(BaseModel):
    """One row of the tumour-board worklist: living patients ranked by 12-month mortality risk."""

    patient_id: str
    name: str
    age: int
    gender: str
    cancer_type: str
    cancer_stage: Optional[str]
    treatment_status: str
    systemic_regimen: Optional[str]
    days_since_diagnosis: Optional[int]
    last_treatment_date: Optional[str]
    mortality_risk_pct: float
    risk_level: str
    drivers: List[str]
    tumor_marker: Optional[str]
    marker_value: Optional[float]
    marker_trend: Optional[str]


class CareGapSummary(BaseModel):
    gap: str
    label: str
    patients: int
    guideline: str


class CareGap(BaseModel):
    patient_id: str
    name: str
    age: int
    gap: str
    label: str
    detail: str
    last_done: Optional[str]


class PatientSummary(BaseModel):
    patient_id: str
    name: str
    age: int
    gender: str
    cancer_type: Optional[str]
    cancer_stage: Optional[str]
    treatment_status: Optional[str]
    clinical_risk_tier: str
    is_deceased: bool


class Patient360(BaseModel):
    patient_id: str
    name: str
    age: int
    gender: str
    blood_group: Optional[str]
    insurance_provider: Optional[str]
    city: Optional[str]
    is_deceased: bool
    death_date: Optional[str]
    clinical_risk_tier: str
    # Oncology summary
    cancer_type: Optional[str]
    cancer_stage: Optional[str]
    diagnosis_date: Optional[str]
    age_at_diagnosis: Optional[int]
    treatment_status: Optional[str]
    systemic_regimen: Optional[str]
    surgery_procedure: Optional[str]
    surgery_date: Optional[str]
    first_treatment_date: Optional[str]
    days_to_treatment: Optional[int]
    chemo_cycles: int
    immunotherapy_cycles: int
    targeted_therapy_cycles: int
    radiation_sessions: int
    tumor_marker: Optional[str]
    marker_value: Optional[float]
    marker_flag: Optional[str]
    marker_trend: Optional[str]
    # Record counts
    total_lab_tests: int
    abnormal_lab_count: int
    critical_lab_count: int
    active_prescriptions: int
    lifetime_billing: float
    comorbidities: List[str]
    flags: Dict[str, bool]
    care_gaps: List[CareGap]


class CarePlan(BaseModel):
    pathway: str
    primary_recommendation: str
    checklist: List[str]
    rationale: List[str]
    disclaimer: str


class SurvivalBenchmark(BaseModel):
    group: str
    patients: int
    one_year_pct: Optional[float]
    five_year_pct: Optional[float]


class PatientRisk(BaseModel):
    available: bool
    scored_as_of: Optional[str]
    mortality_12m_pct: Optional[float]
    risk_level: Optional[str]
    cohort_rate_pct: Optional[float]
    method: Optional[str]
    drivers: List[str]
    survival_benchmark: Optional[SurvivalBenchmark]
    care_plan: CarePlan
    disclaimer: str


class TreatmentEvent(BaseModel):
    event_date: str
    event_type: str
    detail: Optional[str]
    cycle: Optional[int]
    hospital_name: Optional[str]


class LabPoint(BaseModel):
    test_date: str
    test_value: Optional[float]
    abnormal_flag: str


class LabSeries(BaseModel):
    test_name: str
    unit: Optional[str]
    reference_range: Optional[str]
    points: List[LabPoint]


class LabResultRow(BaseModel):
    test_date: str
    test_name: str
    test_value: Optional[float]
    unit: Optional[str]
    reference_range: Optional[str]
    abnormal_flag: str


class MedicationRow(BaseModel):
    prescription_date: str
    end_date: Optional[str]
    medication_name: Optional[str]
    category: Optional[str]
    dosage: Optional[str]
    status: str
    indication: Optional[str]


class EncounterRow(BaseModel):
    admission_id: str
    admission_date: str
    discharge_date: str
    length_of_stay_days: Optional[float]
    admission_type: str
    admission_reason: Optional[str]
    department_name: Optional[str]
    discharge_disposition: str
    surgery_procedure: Optional[str]
    diagnoses: List[str]
