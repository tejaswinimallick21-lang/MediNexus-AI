"""Approval inbox routes (/api/actions/*): actions proposed by Nexa agents, executed only on approval."""

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from backend.app.agents import actions, sweep
from backend.app.core.errors import APIError
from backend.app.jobs import runner
from backend.app.core.deps import current_user
from backend.app.core.users import UserRecord
from backend.app.schemas.actions import ActionInbox, AgentAction, DecisionIn, SweepStatus
from backend.app.schemas.jobs import JobOut
from backend.app.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/actions", tags=["approvals"], responses=ERROR_RESPONSES)
ActionId = Path(..., pattern="^[0-9a-f]{32}$")


@router.get("", response_model=ActionInbox)
def inbox(status: Optional[str] = Query(None, pattern="^(pending|rejected|executed|failed)$"), user: UserRecord = Depends(current_user)) -> ActionInbox:
    return ActionInbox(pending=actions.pending_count(user), items=actions.list_actions(user, status))


@router.post("/{action_id}/approve", response_model=AgentAction)
def approve(body: DecisionIn, action_id: str = ActionId, user: UserRecord = Depends(current_user)) -> AgentAction:
    return AgentAction.model_validate(actions.decide(action_id, True, user, body.note))


@router.post("/{action_id}/reject", response_model=AgentAction)
def reject(body: DecisionIn, action_id: str = ActionId, user: UserRecord = Depends(current_user)) -> AgentAction:
    return AgentAction.model_validate(actions.decide(action_id, False, user, body.note))


def _admin(user: UserRecord) -> None:
    if user.role != "admin":
        raise APIError(403, "forbidden", "Only administrators can run or view the morning sweep.")


@router.get("/sweep", response_model=SweepStatus)
def sweep_status(user: UserRecord = Depends(current_user)) -> SweepStatus:
    _admin(user)
    job = runner.active_job("nexa_sweep")
    return SweepStatus(schedule=f"Daily at {sweep.SWEEP_TIME}", next_run_at=sweep.next_run_at().isoformat(timespec="minutes"),
                       running_job_id=job.job_id if job else None, runs=sweep.recent_runs())


@router.post("/sweep", response_model=JobOut, status_code=202)
def run_sweep_now(user: UserRecord = Depends(current_user)) -> JobOut:
    _admin(user)
    if runner.active_job("nexa_sweep"):
        raise APIError(409, "sweep_running", "A sweep is already running.")
    return runner.submit("nexa_sweep", user.email, lambda ctx: sweep.run_sweep("manual")).to_out()
