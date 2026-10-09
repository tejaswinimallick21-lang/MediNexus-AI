"""
Copilot chat service: routes a message to the role's agent and returns a structured, typed reply.
(Phase 4 replaces the rule-based agents with Claude tool-use agents behind the same contract.)
"""

import time
from typing import Callable, Dict

from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from backend.app.schemas.operations import AgentReply

AGENT_FACTORIES: Dict[str, Callable[[UserRecord], object]] = {}


def _factories() -> Dict[str, Callable[[UserRecord], object]]:
    if not AGENT_FACTORIES:
        from src.agents.healthanalyst_agent import HealthAnalystAgent
        from src.agents.medicare_agent import MediCareAgent
        from src.agents.pharmalab_agent import PharmaLabAgent

        AGENT_FACTORIES.update({
            "medicare": lambda u: MediCareAgent(),
            "pharmalab": lambda u: PharmaLabAgent(role="Pharmacist"),
            "healthanalyst": lambda u: HealthAnalystAgent(),
        })
    return AGENT_FACTORIES


def _strings(value) -> list:
    return [str(v) for v in value] if isinstance(value, (list, tuple)) else ([str(value)] if value else [])


def chat(agent: str, message: str, user: UserRecord) -> AgentReply:
    message = (message or "").strip()
    if not message:
        raise APIError(422, "empty_message", "Type a question for the assistant.")
    if len(message) > 2000:
        raise APIError(422, "message_too_long", "Keep questions under 2,000 characters.")
    factory = _factories().get(agent)
    if factory is None:
        raise APIError(404, "unknown_agent", f"No assistant named '{agent}'.")

    started = time.perf_counter()
    result = factory(user).process_query(message, username=user.email)
    return AgentReply(
        agent=str(result.get("agent", agent)),
        answer=result.get("text_answer") or None,
        facts=_strings(result.get("facts")),
        predictions=_strings(result.get("predictions")),
        recommendations=_strings(result.get("recommendations")),
        evidence=_strings(result.get("evidence")),
        notes=str(result.get("notes") or ""),
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )
