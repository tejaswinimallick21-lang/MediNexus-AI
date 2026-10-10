"""
Approval inbox: actions proposed by Nexa agents, executed only after a person approves.

Who may approve is decided by page access (purchase orders need Pharmacy, follow-ups need the
Clinical Workstation). Every proposal, approval, rejection and execution is written to the audit log.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.app.core.access import can_access
from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from src.security.audit import log_audit_event
from src.utils.database import execute_query, query_df_strict

KIND_PAGE = {"purchase_order": "pharmacy", "follow_up": "doctor"}
KIND_LABEL = {"purchase_order": "Purchase order", "follow_up": "Patient follow-up"}

_ready = False


def _ensure() -> None:
    global _ready
    if _ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS agent_actions (
            action_id VARCHAR, kind VARCHAR, summary VARCHAR, reason VARCHAR, payload VARCHAR,
            agent VARCHAR, session_id VARCHAR, requested_by VARCHAR, status VARCHAR,
            created_at TIMESTAMP, decided_by VARCHAR, decided_at TIMESTAMP, decision_note VARCHAR, result VARCHAR
        )
    """)
    execute_query("""
        CREATE TABLE IF NOT EXISTS care_tasks (
            task_id VARCHAR, patient_id VARCHAR, kind VARCHAR, reason VARCHAR, due_date DATE, status VARCHAR,
            source_action_id VARCHAR, created_by VARCHAR, approved_by VARCHAR, created_at TIMESTAMP
        )
    """)
    _ready = True


@dataclass
class Action:
    action_id: str
    kind: str
    summary: str
    reason: str
    payload: Dict[str, Any]
    agent: str
    session_id: Optional[str]
    requested_by: str
    status: str
    created_at: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    decision_note: Optional[str] = None
    result: Optional[str] = None

    def out(self, user: UserRecord) -> Dict[str, Any]:
        return {**self.__dict__, "kind_label": KIND_LABEL.get(self.kind, self.kind), "can_decide": self.status == "pending" and can_decide(user, self.kind)}


def can_decide(user: UserRecord, kind: str) -> bool:
    return can_access(user.role, KIND_PAGE.get(kind, "__none__"))


def _iso(v: Any) -> Optional[str]:
    return None if v is None or v != v else str(v)[:19].replace(" ", "T")


def _row(r) -> Action:
    return Action(action_id=r.action_id, kind=r.kind, summary=r.summary, reason=r.reason or "", payload=json.loads(r.payload or "{}"),
                  agent=r.agent or "", session_id=r.session_id, requested_by=r.requested_by, status=r.status, created_at=_iso(r.created_at),
                  decided_by=r.decided_by, decided_at=_iso(r.decided_at), decision_note=r.decision_note, result=r.result)


def propose(kind: str, requested_by: UserRecord, agent: str, session_id: Optional[str], payload: Dict[str, Any], reason: str, summary: str) -> Action:
    _ensure()
    if kind not in KIND_PAGE:
        raise ValueError(f"Unknown action kind '{kind}'.")
    a = Action(action_id=uuid.uuid4().hex, kind=kind, summary=summary[:300], reason=(reason or "")[:1000], payload=payload, agent=agent,
               session_id=session_id, requested_by=requested_by.email, status="pending", created_at=datetime.now().isoformat(timespec="seconds"))
    execute_query("INSERT INTO agent_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)",
                  [a.action_id, a.kind, a.summary, a.reason, json.dumps(payload), agent, session_id, a.requested_by, a.status, datetime.now()])
    log_audit_event(username=requested_by.email, role=requested_by.role, action="AGENT_PROPOSED_ACTION", resource=a.action_id, status="PENDING",
                    details=f"{agent}: {a.summary}")
    return a


def _get(action_id: str) -> Action:
    _ensure()
    df = query_df_strict("SELECT * FROM agent_actions WHERE action_id = ?", [action_id])
    if df.empty:
        raise APIError(404, "action_not_found", "No such action.")
    return _row(next(df.itertuples()))


def list_actions(user: UserRecord, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Actions the user may decide on, plus the ones they requested."""
    _ensure()
    kinds = [k for k in KIND_PAGE if can_decide(user, k)]
    where = ["(requested_by = ?" + (f" OR kind IN ({', '.join('?' for _ in kinds)})" if kinds else "") + ")"]
    params: List[Any] = [user.email, *kinds]
    if status:
        where.append("status = ?")
        params.append(status)
    df = query_df_strict(f"SELECT * FROM agent_actions WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", params + [int(limit)])
    return [_row(r).out(user) for r in df.itertuples()]


def pending_count(user: UserRecord) -> int:
    _ensure()
    kinds = [k for k in KIND_PAGE if can_decide(user, k)]
    if not kinds:
        return 0
    df = query_df_strict(f"SELECT COUNT(*) AS n FROM agent_actions WHERE status = 'pending' AND kind IN ({', '.join('?' for _ in kinds)})", kinds)
    return int(df.iloc[0]["n"])


def _execute(a: Action, user: UserRecord) -> str:
    if a.kind == "purchase_order":
        from backend.app.services import pharmacy

        po = pharmacy.create_purchase_order(a.payload["inventory_id"], int(a.payload["quantity"]), user)
        return f"Purchase order {po.po_id} submitted: {po.quantity} units of {po.medication_name} (est. ${po.estimated_cost:,.2f})."
    if a.kind == "follow_up":
        task_id = uuid.uuid4().hex[:12].upper()
        due = date.today() + timedelta(days=int(a.payload.get("due_in_days", 7)))
        execute_query("INSERT INTO care_tasks VALUES (?, ?, 'follow_up', ?, ?, 'open', ?, ?, ?, ?)",
                      [task_id, a.payload["patient_id"], a.reason, due, a.action_id, a.requested_by, user.email, datetime.now()])
        return f"Follow-up task {task_id} created for {a.payload['patient_id']}, due {due.isoformat()}."
    raise APIError(422, "unknown_action", f"Cannot execute '{a.kind}'.")


def decide(action_id: str, approve: bool, user: UserRecord, note: Optional[str] = None) -> Dict[str, Any]:
    a = _get(action_id)
    if not can_decide(user, a.kind):
        raise APIError(403, "forbidden", f"Your role cannot approve {KIND_LABEL.get(a.kind, a.kind).lower()}s.")
    if a.status != "pending":
        raise APIError(409, "already_decided", f"This action was already {a.status}.")
    now = datetime.now()
    if not approve:
        execute_query("UPDATE agent_actions SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? WHERE action_id = ?",
                      [user.email, now, (note or "")[:500], action_id])
        log_audit_event(username=user.email, role=user.role, action="AGENT_ACTION_REJECTED", resource=action_id, status="SUCCESS", details=a.summary)
        return _get(action_id).out(user)
    try:
        result = _execute(a, user)
        status = "executed"
    except APIError as e:
        result, status = f"Approved but execution failed: {e.detail}", "failed"
    execute_query("UPDATE agent_actions SET status = ?, decided_by = ?, decided_at = ?, decision_note = ?, result = ? WHERE action_id = ?",
                  [status, user.email, now, (note or "")[:500], result, action_id])
    log_audit_event(username=user.email, role=user.role, action="AGENT_ACTION_APPROVED", resource=action_id,
                    status="SUCCESS" if status == "executed" else "FAILURE", details=f"{a.summary} -> {result}")
    return _get(action_id).out(user)
