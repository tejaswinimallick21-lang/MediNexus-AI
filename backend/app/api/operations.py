"""Routers for the Laboratory, Pharmacy and Executive workspaces and the copilot chat."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query

from backend.app.core.deps import current_user, require_agent, require_page
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.core.users import UserRecord
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.operations import (
    AgentReply,
    CapacityPlan,
    ClassOutlook,
    CategoryWorkload,
    ChatIn,
    CriticalAlert,
    DemandForecast,
    ExecutiveForecasts,
    ExecutiveKpis,
    LabCapacityPlan,
    LabKpis,
    PharmacyKpis,
    PurchaseOrderIn,
    PurchaseOrderOut,
    ReadmissionDrivers,
    RevenueByDepartment,
    StockLine,
    TrendPoint,
)
from backend.app.services import agents, executive, laboratory, pharmacy

# ---- Laboratory ---------------------------------------------------------------------------------
lab_router = APIRouter(prefix="/lab", tags=["laboratory"], responses=ERROR_RESPONSES, dependencies=[Depends(require_page("laboratory"))])


@lab_router.get("/kpis", response_model=LabKpis)
def lab_kpis() -> LabKpis:
    return laboratory.get_kpis()


@lab_router.get("/workload-by-category", response_model=List[CategoryWorkload])
def lab_workload() -> List[CategoryWorkload]:
    return laboratory.get_workload_by_category()


@lab_router.get("/daily-volume", response_model=List[TrendPoint])
def lab_daily_volume(days: int = Query(180, ge=14, le=730)) -> List[TrendPoint]:
    return laboratory.get_daily_volume(days)


@lab_router.get("/categories", response_model=List[str])
def lab_categories() -> List[str]:
    return laboratory.get_categories()


@lab_router.get("/critical-alerts", response_model=Page[CriticalAlert])
def lab_critical_alerts(params: PageParams = Depends(page_params), category: Optional[str] = Query(None, max_length=80)) -> Page[CriticalAlert]:
    return laboratory.list_critical_alerts(params, category)


@lab_router.get("/categories/{category}/capacity-plan", response_model=LabCapacityPlan)
def lab_capacity_plan(category: str = Path(..., max_length=80)) -> LabCapacityPlan:
    return laboratory.get_capacity_plan(category)


# ---- Pharmacy -----------------------------------------------------------------------------------
pharmacy_router = APIRouter(prefix="/pharmacy", tags=["pharmacy"], responses=ERROR_RESPONSES, dependencies=[Depends(require_page("pharmacy"))])


@pharmacy_router.get("/kpis", response_model=PharmacyKpis)
def pharmacy_kpis() -> PharmacyKpis:
    return pharmacy.get_kpis()


@pharmacy_router.get("/stock", response_model=Page[StockLine])
def pharmacy_stock(
    params: PageParams = Depends(page_params),
    risk: Optional[str] = Query(None, pattern="^(High Risk|Moderate Risk|Safe)$"),
    search: Optional[str] = Query(None, max_length=80),
) -> Page[StockLine]:
    return pharmacy.list_stock(params, risk, search)


@pharmacy_router.get("/risk-by-category", response_model=List[dict])
def pharmacy_risk_by_category() -> List[dict]:
    return pharmacy.get_risk_by_category()


@pharmacy_router.get("/class-outlook", response_model=ClassOutlook)
def pharmacy_class_outlook() -> ClassOutlook:
    return pharmacy.get_class_outlook()


@pharmacy_router.get("/stock/{inventory_id}/forecast", response_model=DemandForecast)
def pharmacy_forecast(inventory_id: str = Path(..., max_length=40)) -> DemandForecast:
    return pharmacy.get_demand_forecast(inventory_id)


@pharmacy_router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
def pharmacy_purchase_order(body: PurchaseOrderIn, user: UserRecord = Depends(current_user)) -> PurchaseOrderOut:
    return pharmacy.create_purchase_order(body.inventory_id, body.quantity, user)


# ---- Executive ----------------------------------------------------------------------------------
executive_router = APIRouter(prefix="/executive", tags=["executive"], responses=ERROR_RESPONSES, dependencies=[Depends(require_page("executive"))])


@executive_router.get("/kpis", response_model=ExecutiveKpis)
def executive_kpis() -> ExecutiveKpis:
    return executive.get_kpis()


@executive_router.get("/admissions-trend", response_model=List[TrendPoint])
def executive_trend(months: int = Query(36, ge=6, le=240)) -> List[TrendPoint]:
    return executive.get_admissions_trend(months)


@executive_router.get("/revenue-by-department", response_model=List[RevenueByDepartment])
def executive_revenue() -> List[RevenueByDepartment]:
    return executive.get_revenue_by_department()


@executive_router.get("/forecasts", response_model=ExecutiveForecasts)
def executive_forecasts() -> ExecutiveForecasts:
    return executive.get_forecasts()


@executive_router.get("/readmission-drivers", response_model=ReadmissionDrivers)
def executive_readmission_drivers() -> ReadmissionDrivers:
    return executive.get_readmission_drivers()


@executive_router.get("/capacity-plan", response_model=CapacityPlan)
def executive_capacity_plan() -> CapacityPlan:
    return executive.get_capacity_plan()


# ---- Copilots -----------------------------------------------------------------------------------
agents_router = APIRouter(prefix="/agents", tags=["agents"], responses=ERROR_RESPONSES)


@agents_router.post("/{agent}/chat", response_model=AgentReply)
def agent_chat(body: ChatIn, agent: str = Path(..., pattern="^(medicare|pharmalab|healthanalyst|ops)$"), user: UserRecord = Depends(current_user)) -> AgentReply:
    require_agent(agent, user)
    return agents.chat(agent, body.message, user)
