"""Nexa assistant routes (/api/assistant/*): agent catalogue and the signed-in user's conversations."""

from typing import List

from fastapi import APIRouter, Depends, Path, Response

from backend.app.core.deps import current_user
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.core.users import UserRecord
from backend.app.agents import memory
from backend.app.schemas.assistant import AssistantAgent, AssistantExchange, AssistantMessage, AssistantSession, MemoryIn, MemoryItem, SessionCreate, SessionRename
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.operations import ChatIn
from backend.app.services import assistant

router = APIRouter(prefix="/assistant", tags=["assistant"], responses=ERROR_RESPONSES)
SessionId = Path(..., pattern="^[0-9a-f]{32}$")
MemoryId = Path(..., pattern="^[0-9a-f]{32}$")


@router.get("/agents", response_model=List[AssistantAgent])
def agents(user: UserRecord = Depends(current_user)) -> List[AssistantAgent]:
    return assistant.list_agents(user)


@router.get("/sessions", response_model=Page[AssistantSession])
def sessions(params: PageParams = Depends(page_params), user: UserRecord = Depends(current_user)) -> Page[AssistantSession]:
    return assistant.list_sessions(user, params)


@router.post("/sessions", response_model=AssistantSession, status_code=201)
def create_session(body: SessionCreate, user: UserRecord = Depends(current_user)) -> AssistantSession:
    return assistant.create_session(body.agent, user)


@router.patch("/sessions/{session_id}", response_model=AssistantSession)
def rename_session(body: SessionRename, session_id: str = SessionId, user: UserRecord = Depends(current_user)) -> AssistantSession:
    return assistant.rename_session(session_id, body.title, user)


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
def delete_session(session_id: str = SessionId, user: UserRecord = Depends(current_user)) -> Response:
    assistant.delete_session(session_id, user)
    return Response(status_code=204)


@router.get("/sessions/{session_id}/messages", response_model=List[AssistantMessage])
def messages(session_id: str = SessionId, user: UserRecord = Depends(current_user)) -> List[AssistantMessage]:
    return assistant.list_messages(session_id, user)


@router.post("/sessions/{session_id}/messages", response_model=AssistantExchange)
def send(body: ChatIn, session_id: str = SessionId, user: UserRecord = Depends(current_user)) -> AssistantExchange:
    return assistant.send_message(session_id, body.message, user)


# ---- long-term memory: what the signed-in user asked Nexa to remember ----

@router.get("/memory", response_model=List[MemoryItem])
def list_memory(user: UserRecord = Depends(current_user)) -> List[MemoryItem]:
    return [MemoryItem(**m) for m in memory.list_for(user)]


@router.post("/memory", response_model=MemoryItem, status_code=201)
def add_memory(body: MemoryIn, user: UserRecord = Depends(current_user)) -> MemoryItem:
    return MemoryItem(**memory.add(user, body.text, source="panel"))


@router.delete("/memory/{memory_id}", status_code=204, response_class=Response)
def delete_memory(memory_id: str = MemoryId, user: UserRecord = Depends(current_user)) -> Response:
    memory.delete(user, memory_id)
    return Response(status_code=204)


@router.delete("/memory", status_code=204, response_class=Response)
def clear_memory(user: UserRecord = Depends(current_user)) -> Response:
    memory.clear(user)
    return Response(status_code=204)
