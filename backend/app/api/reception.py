from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.app.core.deps import require_page
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.reception import (
    AppointmentRow,
    ReceptionFilters,
    ReceptionKpis,
    StatusDistribution,
    WaitInsights,
)
from backend.app.services import reception as svc

router = APIRouter(
    prefix="/reception",
    tags=["reception"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_page("reception"))],
)


@router.get("/kpis", response_model=ReceptionKpis)
def kpis() -> ReceptionKpis:
    return svc.get_kpis()


@router.get("/status-distribution", response_model=StatusDistribution)
def status_distribution() -> StatusDistribution:
    return svc.get_status_distribution()


@router.get("/wait-insights", response_model=WaitInsights)
def wait_insights() -> WaitInsights:
    return svc.get_wait_insights()


@router.get("/filters", response_model=ReceptionFilters)
def filters() -> ReceptionFilters:
    return svc.get_filters()


@router.get("/appointments", response_model=Page[AppointmentRow])
def appointments(
    params: PageParams = Depends(page_params),
    status: Optional[str] = Query(None, max_length=40),
    department: Optional[str] = Query(None, max_length=120),
    visit_type: Optional[str] = Query(None, max_length=40),
) -> Page[AppointmentRow]:
    return svc.list_appointments(params, status=status, department=department, visit_type=visit_type)
