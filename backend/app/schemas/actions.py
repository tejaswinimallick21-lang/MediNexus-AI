"""Schemas for the approval inbox (actions proposed by Nexa agents)."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ActionStatus = Literal["pending", "rejected", "executed", "failed"]


class AgentAction(BaseModel):
    action_id: str
    kind: str
    kind_label: str
    summary: str
    reason: str
    payload: Dict[str, Any]
    agent: str
    session_id: Optional[str] = None
    requested_by: str
    status: ActionStatus
    created_at: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    decision_note: Optional[str] = None
    result: Optional[str] = None
    can_decide: bool


class ActionInbox(BaseModel):
    pending: int
    items: List[AgentAction]


class DecisionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


class SweepRun(BaseModel):
    run_id: str
    trigger: str
    started_at: str
    finished_at: Optional[str] = None
    status: str
    found: int
    proposed: int
    ai_used: bool
    by_kind: Dict[str, int] = {}
    error: Optional[str] = None


class SweepStatus(BaseModel):
    schedule: str
    next_run_at: str
    running_job_id: Optional[str] = None
    runs: List[SweepRun]
