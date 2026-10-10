"""
Long-term memory for Nexa: things a user explicitly asks the assistant to remember.

- Per user (by sign-in email), shared by all of that user's assistants and conversations.
- Explicit only: saved when the user says "remember ..." (remember tool or the panel), never inferred.
- Preferences and standing instructions, not data: memories go into the system prompt as
  preferences and can never serve as a source for numbers or facts about the network.
- No patient data: text with patient IDs, emails, phone numbers, long ID numbers or birth dates is refused.
- Visible and deletable in the "What Nexa remembers" panel; saves and deletes are audited without the text.

Short-term memory is separate: the last few turns of the current conversation (services.assistant._history).
"""

import re
import uuid
from datetime import datetime
from typing import List

from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from src.security.audit import log_audit_event
from src.utils.database import execute_query, query_df_strict

MAX_CHARS = 300
MAX_PER_USER = 30
PROMPT_ITEMS = 20  # newest first; keeps the prompt (and token cost) small

PHI_PATTERNS = [
    (re.compile(r"\bP_\d{1,6}\b", re.I), "a patient ID"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "an email address"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "an ID number"),
    (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "a phone or ID number"),
    (re.compile(r"\b(date of birth|d\.?o\.?b\.?|born on|mrn|medical record number|ssn|social security)\b", re.I), "personal identifiers"),
]

_ready = False


def _ensure() -> None:
    global _ready
    if _ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            memory_id VARCHAR, user_email VARCHAR, text VARCHAR, source VARCHAR, created_at TIMESTAMP
        )
    """)
    _ready = True


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"^(please\s+)?(remember|note|keep in mind)\s+(that\s+|to\s+)?","", t, flags=re.I).strip()
    if not t:
        raise APIError(422, "empty_memory", "Nothing to remember.")
    if len(t) > MAX_CHARS:
        raise APIError(422, "memory_too_long", f"Memories are limited to {MAX_CHARS} characters.")
    for pattern, what in PHI_PATTERNS:
        if pattern.search(t):
            raise APIError(422, "memory_has_identifiers", f"Not saved: it contains {what}. Nexa only remembers preferences, never patient or personal data.")
    return t[0].upper() + t[1:]


def _row(r) -> dict:
    return {"memory_id": r.memory_id, "text": r.text, "source": r.source, "created_at": r.created_at.isoformat(timespec="seconds")}


def list_for(user: UserRecord) -> List[dict]:
    _ensure()
    df = query_df_strict("SELECT memory_id, text, source, created_at FROM agent_memory WHERE user_email = ? ORDER BY created_at DESC", [user.email])
    return [_row(r) for r in df.itertuples()]


def add(user: UserRecord, text: str, source: str = "panel") -> dict:
    """Save one memory; an identical one (ignoring case) is returned instead of duplicated."""
    _ensure()
    t = _clean(text)
    existing = list_for(user)
    same = next((m for m in existing if m["text"].lower() == t.lower()), None)
    if same:
        return same
    if len(existing) >= MAX_PER_USER:
        raise APIError(409, "memory_full", f"Nexa already remembers {MAX_PER_USER} things for you. Delete some in 'What Nexa remembers' first.")
    memory_id, now = uuid.uuid4().hex, datetime.now()
    execute_query("INSERT INTO agent_memory (memory_id, user_email, text, source, created_at) VALUES (?, ?, ?, ?, ?)",
                  [memory_id, user.email, t, source, now])
    log_audit_event(username=user.email, role=user.role, action="MEMORY_SAVE", resource=memory_id, details=f"source={source}")
    return {"memory_id": memory_id, "text": t, "source": source, "created_at": now.isoformat(timespec="seconds")}


def delete(user: UserRecord, memory_id: str) -> None:
    _ensure()
    if query_df_strict("SELECT 1 FROM agent_memory WHERE memory_id = ? AND user_email = ?", [memory_id, user.email]).empty:
        raise APIError(404, "memory_not_found", "That memory does not exist.")
    execute_query("DELETE FROM agent_memory WHERE memory_id = ?", [memory_id])
    log_audit_event(username=user.email, role=user.role, action="MEMORY_DELETE", resource=memory_id)


def clear(user: UserRecord) -> int:
    _ensure()
    n = len(list_for(user))
    execute_query("DELETE FROM agent_memory WHERE user_email = ?", [user.email])
    log_audit_event(username=user.email, role=user.role, action="MEMORY_CLEAR", resource="agent_memory", details=f"deleted={n}")
    return n


def prompt_block(user: UserRecord) -> str:
    items = list_for(user)[:PROMPT_ITEMS]
    if not items:
        return ""
    lines = "\n".join(f"- {m['text']}" for m in items)
    return ("What this user asked you to remember (preferences and standing instructions; follow them where they apply, "
            "but they are NOT data: never use them as a source for numbers or facts about the network):\n" + lines)
