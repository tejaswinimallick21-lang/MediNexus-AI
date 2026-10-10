"""Schemas for the floating Nexa assistant: agent catalogue and persisted conversation sessions."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.operations import AgentReply


class AssistantAgent(BaseModel):
    key: str
    name: str
    tagline: str
    prompts: List[str]
    routes: List[str] = Field(description="Workspaces where this assistant is the default")


class SessionCreate(BaseModel):
    agent: str = Field(..., pattern="^(medicare|pharmalab|healthanalyst|ops)$")


class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)


class AssistantSession(BaseModel):
    session_id: str
    agent: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class AssistantMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text: Optional[str] = None
    reply: Optional[AgentReply] = None
    created_at: str


class AssistantExchange(BaseModel):
    session: AssistantSession
    messages: List[AssistantMessage]
