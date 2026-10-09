"""Schemas for the HCP Clinical Workstation (Care Console)."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class ClinicalKpis(BaseModel):
    living_patients: int
    high_tier_patients: int
    recent_discharges: int
    high_risk_recent_discharges: int
    open_care_gaps: int
    data_through: str


class HuddlePatient(BaseModel):
    patient_id: str
    name: str
    age: int
    gender: str
    admission_id: str
    discharge_date: str
    admission_reason: Optional[str]
    department_name: Optional[str]
    readmission_probability_pct: float
    risk_level: str
    drivers: List[str]
    has_follow_up: bool


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
    clinical_risk_tier: str
    total_admissions: int
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
    total_admissions: int
    average_los_days: float
    unplanned_readmissions: int
    total_lab_tests: int
    abnormal_lab_count: int
    critical_lab_count: int
    active_prescriptions: int
    lifetime_billing: float
    comorbidities: List[str]
    flags: Dict[str, bool]
    care_gaps: List[CareGap]


class OutcomeRisk(BaseModel):
    outcome: str
    label: str
    probability_pct: float
    risk_level: str
    cohort_rate_pct: float
    observed: Optional[int]


class CarePlan(BaseModel):
    pathway: str
    primary_recommendation: str
    checklist: List[str]
    rationale: List[str]
    disclaimer: str


class PatientRisk(BaseModel):
    covid_scored_as_of: Optional[str]
    covid_outcomes: List[OutcomeRisk]
    covid_drivers: List[str]
    readmission_available: bool
    readmission_probability_pct: Optional[float]
    readmission_risk_level: Optional[str]
    readmission_base_rate_pct: Optional[float]
    readmission_drivers: List[str]
    readmission_admission_date: Optional[str]
    los_predicted_days: Optional[float]
    los_observed_days: Optional[float]
    los_interval: Optional[str]
    care_plan: CarePlan
    disclaimer: str


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
    is_icu: bool
    readmitted_30d: bool
    diagnoses: List[str]
