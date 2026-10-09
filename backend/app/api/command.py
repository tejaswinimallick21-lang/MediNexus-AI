"""Analyst Command Center routes (/api/command/*): analyst role, admins oversee."""

from typing import List

from fastapi import APIRouter, Depends

from backend.app.core.deps import require_page
from backend.app.schemas.command import HospitalOption, ModelMonitorRow, ReadmissionEconomics, WhatIfIn, WhatIfResult
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.services import command

router = APIRouter(prefix="/command", tags=["command-center"], responses=ERROR_RESPONSES, dependencies=[Depends(require_page("command"))])


@router.get("/hospitals", response_model=List[HospitalOption])
def hospitals() -> List[HospitalOption]:
    return command.list_hospitals()


@router.post("/what-if", response_model=WhatIfResult)
def what_if(body: WhatIfIn) -> WhatIfResult:
    return command.run_what_if(body)


@router.get("/readmission-economics", response_model=ReadmissionEconomics)
def readmission_economics() -> ReadmissionEconomics:
    return command.get_readmission_economics()


@router.get("/models", response_model=List[ModelMonitorRow])
def models() -> List[ModelMonitorRow]:
    return command.list_model_monitor()
