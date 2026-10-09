"""Schemas for the Laboratory, Pharmacy and Executive workspaces and shared forecast/model metadata."""

from typing import List, Optional

from pydantic import BaseModel


class ForecastMeta(BaseModel):
    """How a forecast was produced and how well that method did on held-out data."""

    serving_method: str
    method_label: str
    holdout_mae: Optional[float] = None
    holdout_baseline_mae: Optional[float] = None
    beats_baseline: Optional[bool] = None
    test_period: Optional[str] = None
    data_through: Optional[str] = None


class TrendPoint(BaseModel):
    period: str
    value: float
    secondary: Optional[float] = None


# ---- Laboratory --------------------------------------------------------------------------------

class LabKpis(BaseModel):
    total_tests: int
    abnormal_tests: int
    critical_tests: int
    abnormal_pct: float
    critical_pct: float
    tests_last_30d: int


class CategoryWorkload(BaseModel):
    category: str
    total: int
    abnormal: int
    critical: int


class CriticalAlert(BaseModel):
    lab_id: str
    patient_id: str
    test_name: str
    test_value: Optional[float]
    unit: Optional[str]
    reference_range: Optional[str]
    test_date: str
    department_name: Optional[str]


class LabCapacityPlan(BaseModel):
    category: str
    forecast_daily_tests: float
    last_7d_daily: float
    estimated_capacity_daily: int
    utilization_pct: float
    critical_rate_pct: float
    operational_status: str
    actions: List[str]
    assessment: str
    forecast: ForecastMeta


# ---- Pharmacy ----------------------------------------------------------------------------------

class PharmacyKpis(BaseModel):
    stock_lines: int
    high_risk_lines: int
    moderate_risk_lines: int
    dispensed_units_180d: int
    active_prescriptions: int


class StockLine(BaseModel):
    inventory_id: str
    medication_id: str
    medication_name: Optional[str]
    category: Optional[str]
    hospital_id: Optional[str]
    hospital_name: Optional[str]
    stock_quantity: int
    reorder_level: int
    days_of_supply: Optional[float]
    stockout_risk: str


class DemandForecast(BaseModel):
    inventory_id: str
    medication_name: str
    hospital_name: Optional[str]
    current_stock: int
    dispensed_last_30d: int
    predicted_30d_demand: int
    projected_shortfall: int
    urgency: str
    recommended_order_quantity: int
    estimated_procurement_cost: float
    actions: List[str]
    buffer_assessment: str
    forecast: ForecastMeta


class ClassOutlookRow(BaseModel):
    drug_class: str
    forecast_daily_units: float
    last_7d_daily_units: float
    change_pct: float


class ClassOutlook(BaseModel):
    simulated_data: bool
    as_of: str
    items: List[ClassOutlookRow]
    forecast: ForecastMeta


class PurchaseOrderIn(BaseModel):
    inventory_id: str
    quantity: int


class PurchaseOrderOut(BaseModel):
    po_id: str
    inventory_id: str
    medication_name: str
    quantity: int
    estimated_cost: float
    status: str
    created_at: str


# ---- Executive ---------------------------------------------------------------------------------

class ExecutiveKpis(BaseModel):
    total_admissions: int
    patients_admitted: int
    unplanned_readmission_rate_pct: float
    average_los_days: float
    occupancy_rate_pct: Optional[float]
    total_revenue: float
    collection_rate_pct: float
    hospitals: int
    data_through: str


class RevenueByDepartment(BaseModel):
    department: str
    revenue: float
    admissions: int


class ModelScore(BaseModel):
    model: str
    purpose: str
    primary_metric: str
    baseline: str
    verdict: str


class ExecutiveForecasts(BaseModel):
    admissions_next_7d_daily: float
    admissions_last_7d_daily: float
    admissions_forecast: ForecastMeta
    models: List[ModelScore]


class ReadmissionBreakdownRow(BaseModel):
    label: str
    count: int
    rate_pct: float


class ReadmissionDrivers(BaseModel):
    summary: str
    findings: List[str]
    by_admission_type: List[ReadmissionBreakdownRow]
    by_reason: List[ReadmissionBreakdownRow]


class CapacityPlan(BaseModel):
    surge_tier: str
    occupancy_pct: Optional[float]
    projected_daily_admissions: float
    average_los_days: float
    directives: List[str]
    assessment: str
    occupancy_note: str


# ---- Agents ------------------------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str


class AgentReply(BaseModel):
    agent: str
    answer: Optional[str] = None
    facts: List[str]
    predictions: List[str]
    recommendations: List[str]
    evidence: List[str]
    notes: str
    latency_ms: float
