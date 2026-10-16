"""Schemas for the Analyst Command Center: what-if capacity simulation and model monitor."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Period = Literal["last_90", "last_365"]


class HospitalOption(BaseModel):
    hospital_id: str
    hospital_name: str
    beds: int
    physicians: int
    avg_daily_demand: float
    served_pct: float
    avg_wait_days: float


class WhatIfIn(BaseModel):
    hospital_id: Optional[str] = Field(None, max_length=60, description="Omit for the whole network")
    period: Period = "last_365"
    extra_visits_per_physician: float = Field(0, ge=0, le=15, description="Additional outpatient visits per on-duty physician per day")
    extra_physicians: int = Field(0, ge=0, le=50, description="Additional physicians per hospital")
    demand_change_pct: float = Field(0, ge=-50, le=100, description="Change in outpatient demand")


class WhatIfSide(BaseModel):
    demand: int
    served: int
    lost_to_follow_up: int
    avg_backlog: float
    avg_wait_days: float
    utilization_pct: float
    visits_per_physician_day: float
    revenue: float
    staffing_cost: float


class WhatIfDay(BaseModel):
    date: str
    baseline_backlog: float
    scenario_backlog: float
    baseline_served: float
    scenario_served: float


class WhatIfResult(BaseModel):
    simulated_data: bool
    scope: str
    period_start: str
    period_end: str
    days: int
    baseline: WhatIfSide
    scenario: WhatIfSide
    net_impact: float
    net_impact_per_month: float
    insights: List[str]
    assumptions: List[str]
    daily: List[WhatIfDay]


class ModelMonitorRow(BaseModel):
    model_name: str
    label: str
    version: str
    trained_at: str
    age_days: int
    data_source: str
    primary_metric: str
    baseline: str
    verdict: str
    serving: str
    health: Literal["healthy", "baseline", "low_evidence"]
    note: str
    versions: int
