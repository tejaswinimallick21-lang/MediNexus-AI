"""
Copilot chat service: routes a message to the role's Nexa agent (LLM + scoped tools, or the
rules engine when no LLM key is configured) and returns a structured, typed reply.
"""

from typing import List, Optional, Tuple

from backend.app.agents import engine
from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from backend.app.schemas.operations import AgentReply

AGENTS = ("medicare", "pharmalab", "healthanalyst", "ops")


def chat(agent: str, message: str, user: UserRecord, history: Optional[List[Tuple[str, str]]] = None, session_id: Optional[str] = None) -> AgentReply:
    message = (message or "").strip()
    if not message:
        raise APIError(422, "empty_message", "Type a question for the assistant.")
    if len(message) > 2000:
        raise APIError(422, "message_too_long", "Keep questions under 2,000 characters.")
    if agent not in AGENTS:
        raise APIError(404, "unknown_agent", f"No assistant named '{agent}'.")
    return AgentReply.model_validate(engine.run(agent, message, user, history=history, session_id=session_id))
