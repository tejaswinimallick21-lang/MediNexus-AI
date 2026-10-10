"""
Learning from approval decisions ("decision memory").

Every proposal carries a context (site and medication for orders, risk band for follow-ups,
test name for lab escalations). Before proposing again, the agents look up how people decided
on similar proposals:

- history is always shown with the proposal ("3 of 4 similar orders for this site were rejected:
  'covered by central store'"), so approvers see the pattern;
- the scheduled sweep stops proposing a kind of item people keep rejecting
  (>= MIN_DECISIONS decided, rejection share >= SUPPRESS_RATE);
- except where safety wins: critical lab escalations are never suppressed, and an order for a
  medicine that is completely out of stock is still proposed, with the history attached.

No patient data is learned: only the decision, the context labels above and the reviewer's note.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.utils.database import query_df_strict

MIN_DECISIONS = int(os.getenv("NEXA_LEARNING_MIN_DECISIONS", "3"))
SUPPRESS_RATE = float(os.getenv("NEXA_LEARNING_SUPPRESS_RATE", "0.75"))
NEVER_SUPPRESS = {"lab_escalation"}


def risk_band(probability_pct: Optional[float]) -> str:
    if probability_pct is None:
        return "unknown"
    return "very high (60%+)" if probability_pct >= 60 else "high (40-60%)" if probability_pct >= 40 else "moderate (<40%)"


def context_for(kind: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """The labels similarity is judged on (kept in the proposal's payload)."""
    ctx = payload.get("context") or {}
    if ctx:
        return ctx
    if kind == "lab_escalation" and payload.get("test_name"):
        return {"test": str(payload["test_name"])}
    return {}


SIMILAR_ON = {  # kind -> context fields that make two proposals "similar" (any one matching)
    "purchase_order": ("site", "medication"),
    "follow_up": ("risk_band",),
    "lab_escalation": ("test",),
}


@dataclass
class History:
    approved: int
    rejected: int
    notes: List[str]
    matched_on: str

    @property
    def decided(self) -> int:
        return self.approved + self.rejected

    @property
    def rejection_rate(self) -> float:
        return self.rejected / self.decided if self.decided else 0.0

    def summary(self) -> str:
        if not self.decided:
            return ""
        s = f"History: of {self.decided} similar proposal{'s' if self.decided != 1 else ''} ({self.matched_on}), {self.approved} approved and {self.rejected} rejected"
        if self.notes:
            s += f"; reviewer notes: {'; '.join(repr(n) for n in self.notes[:2])}"
        return s + "."


def history_for(kind: str, context: Dict[str, str]) -> History:
    """Decided proposals of the same kind sharing any similarity field, most specific field first."""
    fields = [f for f in SIMILAR_ON.get(kind, ()) if context.get(f)]
    if not fields:
        return History(0, 0, [], "")
    df = query_df_strict("SELECT status, payload, decision_note FROM agent_actions WHERE kind = ? AND status IN ('executed', 'failed', 'rejected')", [kind])
    for f in fields:
        approved = rejected = 0
        notes: List[str] = []
        for r in df.itertuples():
            try:
                other = context_for(kind, json.loads(r.payload or "{}"))
            except ValueError:
                continue
            if other.get(f) != context[f]:
                continue
            if r.status == "rejected":
                rejected += 1
                if isinstance(r.decision_note, str) and r.decision_note.strip():  # empty notes come back as NA
                    notes.append(r.decision_note.strip()[:120])
            else:
                approved += 1
        if approved + rejected:
            return History(approved, rejected, notes, f"same {f.replace('_', ' ')}: {context[f]}")
    return History(0, 0, [], "")


def should_suppress(kind: str, history: History, urgent: bool = False) -> bool:
    if kind in NEVER_SUPPRESS or urgent:
        return False
    return history.decided >= MIN_DECISIONS and history.rejection_rate >= SUPPRESS_RATE
