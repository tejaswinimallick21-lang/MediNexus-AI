from typing import List, Optional

from pydantic import BaseModel

from backend.app.schemas.common import LabelCount


class ReceptionKpis(BaseModel):
    total_appointments: int
    completed: int
    no_shows: int
    cancelled: int
    no_show_rate_pct: float
    cancellation_rate_pct: float
    avg_wait_minutes: float


class HourlyWait(BaseModel):
    hour: str
    volume: int
    avg_wait_min: float


class WaitInsights(BaseModel):
    summary: str
    findings: List[str]
    by_hour: List[HourlyWait]
    wait_times_simulated: bool
    target_wait_minutes: int


class ReceptionFilters(BaseModel):
    statuses: List[str]
    departments: List[str]
    visit_types: List[str]


class AppointmentRow(BaseModel):
    """Front-desk view: no diagnoses, reasons or lab data (POL-HOSP-003)."""

    appointment_id: str
    patient_name: Optional[str]
    contact: Optional[str]
    appointment_date: str
    appointment_time: Optional[str]
    doctor_name: Optional[str]
    department_name: Optional[str]
    visit_type: Optional[str]
    status: str
    waiting_time_minutes: Optional[int]


class StatusDistribution(BaseModel):
    items: List[LabelCount]
