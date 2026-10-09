"""
Nexa assistant service: the agent catalogue each role may use and persisted conversation history.

Sessions belong to one user; another user's session id behaves as not found. Deleting a session
hides it (deleted_at) so the conversation remains available to audit.
"""

import json
import uuid
from datetime import datetime
from typing import List

from backend.app.core.access import AGENT_ROLES
from backend.app.core.deps import require_agent
from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.core.users import UserRecord
from backend.app.schemas.assistant import AssistantAgent, AssistantExchange, AssistantMessage, AssistantSession
from backend.app.schemas.operations import AgentReply
from backend.app.services import agents
from src.utils.database import execute_query, query_df_strict

TITLE_MAX = 60

CATALOG = [
    AssistantAgent(
        key="medicare", name="Nexa Care", tagline="Clinical assistant grounded in Patient 360, risk models and care guidelines",
        prompts=["Show me the highest-risk patients", "Summarize patient P_04436", "What does the heart failure follow-up guideline say?"],
        routes=["/doctor"],
    ),
    AssistantAgent(
        key="pharmalab", name="Nexa Care · Lab & Pharmacy", tagline="Laboratory and formulary data plus lab safety and cold-chain policy",
        prompts=["Which medicines require immediate replenishment?", "Which laboratory alerts need escalation?", "What are the temperature standards for refrigerated medications?"],
        routes=["/pharmacy", "/laboratory"],
    ),
    AssistantAgent(
        key="healthanalyst", name="Nexa Insight", tagline="Operations analytics grounded in Gold marts and hospital policy",
        prompts=["Why did readmissions increase across inpatient wards?", "Provide bed capacity and surge forecast", "What are the inpatient discharge guidelines?"],
        routes=["/executive", "/command-center", "/reception"],
    ),
]

_tables_ready = False


def _ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS assistant_sessions (
            session_id VARCHAR, user_email VARCHAR, agent VARCHAR, title VARCHAR,
            created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP
        )
    """)
    execute_query("""
        CREATE TABLE IF NOT EXISTS assistant_messages (
            message_id VARCHAR, session_id VARCHAR, role VARCHAR, content VARCHAR, created_at TIMESTAMP
        )
    """)
    _tables_ready = True


def list_agents(user: UserRecord) -> List[AssistantAgent]:
    return [a for a in CATALOG if user.role in AGENT_ROLES.get(a.key, frozenset())]


def _iso(ts) -> str:
    return str(ts)[:19].replace(" ", "T")


def _session_row(session_id: str, user: UserRecord) -> AssistantSession:
    df = query_df_strict("""
        SELECT s.session_id, s.agent, s.title, s.created_at, s.updated_at,
               (SELECT COUNT(*) FROM assistant_messages m WHERE m.session_id = s.session_id) AS n
        FROM assistant_sessions s WHERE s.session_id = ? AND s.user_email = ? AND s.deleted_at IS NULL
    """, [session_id, user.email])
    if df.empty:
        raise APIError(404, "session_not_found", "That conversation does not exist.")
    r = df.iloc[0]
    return AssistantSession(session_id=r["session_id"], agent=r["agent"], title=r["title"], created_at=_iso(r["created_at"]),
                            updated_at=_iso(r["updated_at"]), message_count=int(r["n"]))


def list_sessions(user: UserRecord, params: PageParams) -> Page[AssistantSession]:
    _ensure_tables()
    df = query_df_strict("""
        SELECT s.session_id, s.agent, s.title, s.created_at, s.updated_at,
               (SELECT COUNT(*) FROM assistant_messages m WHERE m.session_id = s.session_id) AS n
        FROM assistant_sessions s WHERE s.user_email = ? AND s.deleted_at IS NULL
        ORDER BY s.updated_at DESC, s.session_id LIMIT ? OFFSET ?
    """, [user.email, params.limit + 1, params.offset])
    rows = [
        AssistantSession(session_id=r.session_id, agent=r.agent, title=r.title, created_at=_iso(r.created_at), updated_at=_iso(r.updated_at), message_count=int(r.n))
        for r in df.itertuples()
    ]
    return build_page(rows, params)


def create_session(agent: str, user: UserRecord) -> AssistantSession:
    require_agent(agent, user)
    _ensure_tables()
    now = datetime.now()
    session_id = uuid.uuid4().hex
    execute_query("INSERT INTO assistant_sessions VALUES (?, ?, ?, ?, ?, ?, NULL)", [session_id, user.email, agent, "New conversation", now, now])
    return _session_row(session_id, user)


def rename_session(session_id: str, title: str, user: UserRecord) -> AssistantSession:
    _ensure_tables()
    _session_row(session_id, user)
    execute_query("UPDATE assistant_sessions SET title = ? WHERE session_id = ?", [title.strip()[:80], session_id])
    return _session_row(session_id, user)


def delete_session(session_id: str, user: UserRecord) -> None:
    _ensure_tables()
    _session_row(session_id, user)
    execute_query("UPDATE assistant_sessions SET deleted_at = ? WHERE session_id = ?", [datetime.now(), session_id])


def _message(r) -> AssistantMessage:
    if r.role == "assistant":
        return AssistantMessage(message_id=r.message_id, role="assistant", reply=AgentReply.model_validate(json.loads(r.content)), created_at=_iso(r.created_at))
    return AssistantMessage(message_id=r.message_id, role="user", text=r.content, created_at=_iso(r.created_at))


def list_messages(session_id: str, user: UserRecord) -> List[AssistantMessage]:
    _ensure_tables()
    _session_row(session_id, user)
    df = query_df_strict(
        "SELECT message_id, role, content, created_at FROM assistant_messages WHERE session_id = ? ORDER BY created_at, role DESC",
        [session_id],
    )
    return [_message(r) for r in df.itertuples()]


def send_message(session_id: str, message: str, user: UserRecord) -> AssistantExchange:
    _ensure_tables()
    session = _session_row(session_id, user)
    require_agent(session.agent, user)
    reply = agents.chat(session.agent, message, user)  # validates the message before anything is stored

    asked_at, now = datetime.now(), datetime.now()
    question = message.strip()
    user_id, reply_id = uuid.uuid4().hex, uuid.uuid4().hex
    execute_query("INSERT INTO assistant_messages VALUES (?, ?, 'user', ?, ?)", [user_id, session_id, question, asked_at])
    execute_query("INSERT INTO assistant_messages VALUES (?, ?, 'assistant', ?, ?)", [reply_id, session_id, reply.model_dump_json(), now])
    if session.message_count == 0 and session.title == "New conversation":
        title = question if len(question) <= TITLE_MAX else question[: TITLE_MAX - 1].rstrip() + "…"
        execute_query("UPDATE assistant_sessions SET title = ?, updated_at = ? WHERE session_id = ?", [title, now, session_id])
    else:
        execute_query("UPDATE assistant_sessions SET updated_at = ? WHERE session_id = ?", [now, session_id])
    return AssistantExchange(
        session=_session_row(session_id, user),
        messages=[
            AssistantMessage(message_id=user_id, role="user", text=question, created_at=_iso(asked_at)),
            AssistantMessage(message_id=reply_id, role="assistant", reply=reply, created_at=_iso(now)),
        ],
    )
