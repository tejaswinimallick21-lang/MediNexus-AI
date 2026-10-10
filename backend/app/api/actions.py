"""Approval inbox routes (/api/actions/*): actions proposed by Nexa agents, executed only on approval."""

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from backend.app.agents import actions
from backend.app.core.deps import current_user
from backend.app.core.users import UserRecord
from backend.app.schemas.actions import ActionInbox, AgentAction, DecisionIn
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
