"""
Learning from approval decisions: history lookup, suppression rules, safety exceptions, and
the sweep and chat proposals using it. Runs on the isolated test database copy.
"""

import json

import pytest

from backend.app.agents import actions, learning, sweep
from src.utils.database import execute_query, query_df_strict


@pytest.fixture()
def seeded():
    """Create decided proposals; removed afterwards so other tests see a clean history."""
    made = []

    def add(kind, context, status, note=""):
        a = actions._propose_raw(kind, "test@medinexus.org", "admin", "test", "learning-test", {"context": context}, "seed", f"seed {kind}")
        execute_query("UPDATE agent_actions SET status = ?, decision_note = ? WHERE action_id = ?", [status, note, a.action_id])
        made.append(a.action_id)

    yield add
    for i in made:
        execute_query("DELETE FROM agent_actions WHERE action_id = ?", [i])
    execute_query("DELETE FROM agent_actions WHERE session_id LIKE 'sweep:%'")


def test_history_counts_similar_decisions(seeded):
    seeded("purchase_order", {"site": "Site A", "medication": "Drug X"}, "rejected", "covered by central store")
    seeded("purchase_order", {"site": "Site A", "medication": "Drug Y"}, "rejected")
    seeded("purchase_order", {"site": "Site A", "medication": "Drug Z"}, "executed")
    seeded("purchase_order", {"site": "Site B", "medication": "Drug Q"}, "rejected")
    h = learning.history_for("purchase_order", {"site": "Site A", "medication": "Drug W"})
    assert (h.approved, h.rejected) == (1, 2) and "same site: Site A" in h.summary()
    assert "covered by central store" in h.summary()
    assert learning.history_for("purchase_order", {"site": "Nowhere", "medication": "None"}).decided == 0


def test_suppression_rules_and_safety_exceptions(seeded):
    for _ in range(3):
        seeded("purchase_order", {"site": "Site C", "medication": "Drug R"}, "rejected")
        seeded("lab_escalation", {"test": "Creatinine"}, "rejected")
    po = learning.history_for("purchase_order", {"site": "Site C", "medication": "Drug R"})
    lab = learning.history_for("lab_escalation", {"test": "Creatinine"})
    assert learning.should_suppress("purchase_order", po) is True
    assert learning.should_suppress("purchase_order", po, urgent=True) is False  # out of stock: still proposed
    assert learning.should_suppress("lab_escalation", lab) is False  # patient safety: never suppressed
    mixed = learning.History(approved=2, rejected=1, notes=[], matched_on="x")
    assert learning.should_suppress("purchase_order", mixed) is False


def test_sweep_skips_what_people_keep_rejecting(seeded, monkeypatch):
    band = "moderate (<40%)"  # most patients waiting for treatment have a predicted mortality under 40%
    for _ in range(3):
        seeded("follow_up", {"risk_band": band}, "rejected", "patients already have specialist follow-up")
    monkeypatch.setattr(sweep, "MAX_PROPOSALS", 30)
    r = sweep.run_sweep("manual")
    rows = query_df_strict("SELECT kind, payload, reason FROM agent_actions WHERE session_id = ?", [f"sweep:{r['run_id']}"])
    bands = [json.loads(p).get("context", {}).get("risk_band") for k, p in zip(rows["kind"], rows["payload"]) if k == "follow_up"]
    assert band not in bands and r["suppressed"] > 0
    assert (rows["kind"] == "lab_escalation").any()  # unaffected
    assert sweep.recent_runs(1)[0]["suppressed"] == r["suppressed"]


def test_proposals_carry_their_history(seeded, monkeypatch):
    seeded("follow_up", {"risk_band": "moderate (<40%)"}, "executed")
    seeded("follow_up", {"risk_band": "moderate (<40%)"}, "rejected", "duplicate booking")
    monkeypatch.setattr(sweep, "MAX_PROPOSALS", 30)
    r = sweep.run_sweep("manual")
    rows = query_df_strict("SELECT payload, reason FROM agent_actions WHERE session_id = ? AND kind = 'follow_up'", [f"sweep:{r['run_id']}"])
    moderate = [reason for p, reason in zip(rows["payload"], rows["reason"]) if json.loads(p)["context"]["risk_band"] == "moderate (<40%)"]
    assert moderate, "the data has untreated patients diagnosed more than 30 days ago"
    assert all("1 approved and 1 rejected" in x and "duplicate booking" in x for x in moderate)
