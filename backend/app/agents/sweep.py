"""
Nexa morning sweep: a scheduled agent run that looks for work nobody has picked up yet and
prepares proposals for people to approve.

    1. Detect (plain database checks, free):
       - high-risk recent discharges with no follow-up booked
       - stock lines at high stock-out risk with no pending or recent purchase order
       - recent critical lab values not yet escalated
    2. Justify: the LLM words one evidence-based sentence per proposal from the facts we pass in
       (no tools, short reply, daily cap). Without an LLM, a template states the same facts.
    3. Propose: each item lands in the approval inbox; nothing runs until a person approves.

Never proposes the same thing twice while it is pending or done.
"""

import json
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.agents import actions, learning, providers
from backend.app.core.pagination import PageParams
from src.utils.database import execute_query, query_df_strict
from src.utils.logging_utils import get_logger

logger = get_logger("nexa_sweep")

MAX_PROPOSALS = int(os.getenv("NEXA_SWEEP_MAX", "20"))  # per run (also caps LLM calls)
SWEEP_TIME = os.getenv("NEXA_SWEEP_TIME", "07:00")  # local time, daily
AGENT = "sweep"

JUSTIFY_SYSTEM = (
    "You write one or two sentences justifying a proposed hospital action for the person who must approve it. "
    "Use ONLY the facts given; do not add numbers, diagnoses or advice that are not in them. Mention the key figures. "
    "End with what approving will do. Plain language, no preamble."
)

_ready = False


def _ensure() -> None:
    global _ready
    if _ready:
        return
    execute_query("""
        CREATE TABLE IF NOT EXISTS sweep_runs (
            run_id VARCHAR, trigger VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR,
            found INTEGER, proposed INTEGER, skipped_duplicates INTEGER, ai_used BOOLEAN, error VARCHAR, details VARCHAR
        )
    """)
    execute_query("ALTER TABLE sweep_runs ADD COLUMN IF NOT EXISTS suppressed INTEGER")
    _ready = True


# ---- 1. detect ------------------------------------------------------------------------------------

def _follow_up_candidates() -> List[Dict[str, Any]]:
    from backend.app.services import clinical

    taken = actions.open_keys("follow_up", "patient_id")
    try:
        taken |= set(query_df_strict("SELECT patient_id FROM care_tasks WHERE kind = 'follow_up' AND status = 'open'")["patient_id"])
    except Exception:  # care_tasks not created yet
        pass
    out = []
    # Diagnosed more than 30 days ago and no treatment yet: propose a visit to start treatment
    gaps = clinical._all_gaps()
    delayed = gaps[gaps["gap"] == "treatment_delay"]
    if delayed.empty:
        return out
    scored = clinical._scored_living().set_index("patient_id")
    for g in delayed.itertuples():
        if g.patient_id in taken or g.patient_id not in scored.index:
            continue
        p = scored.loc[g.patient_id]
        risk_pct = round(float(p["mortality_risk"]) * 100, 1)
        days = int((clinical._data_end() - pd.to_datetime(p["diagnosis_date"])).days)
        out.append({
            "kind": "follow_up", "key": g.patient_id, "priority": days + risk_pct,
            "payload": {"patient_id": g.patient_id, "due_in_days": 7, "context": {"risk_band": learning.risk_band(risk_pct)}},
            "summary": f"Follow-up for {g.patient_id} within 7 days to start treatment ({days} days since diagnosis)",
            "facts": {"patient_id": g.patient_id, "age": int(p["age"]), "cancer_type": p["cancer_type"], "stage": p["cancer_stage"],
                      "diagnosed": p["diagnosis_date"], "days_since_diagnosis": days, "treatment_started": False,
                      "predicted_12m_mortality_pct": risk_pct, "guideline": "First treatment within 30 days of diagnosis (time-to-treatment standard)"},
        })
    return out


def _stock_candidates() -> List[Dict[str, Any]]:
    from backend.app.services import pharmacy

    taken = actions.open_keys("purchase_order", "inventory_id")
    try:
        taken |= set(query_df_strict("SELECT inventory_id FROM purchase_orders WHERE created_at > now() - INTERVAL 7 DAY")["inventory_id"])
    except Exception:
        pass
    out = []
    for line in pharmacy.list_stock(PageParams(limit=40), "High Risk", None).items:
        if line.inventory_id in taken:
            continue
        f = pharmacy.get_demand_forecast(line.inventory_id)
        if f.recommended_order_quantity <= 0:
            continue
        out.append({
            "kind": "purchase_order", "key": line.inventory_id, "priority": 50 - (line.days_of_supply or 0),
            "payload": {"inventory_id": line.inventory_id, "quantity": int(f.recommended_order_quantity),
                        "context": {"site": line.hospital_name or "", "medication": line.medication_name or ""}},
            "urgent": (line.stock_quantity or 0) <= 0,  # out of stock: propose even against past rejections
            "summary": f"Purchase order: {int(f.recommended_order_quantity)} units of {line.medication_name} for {line.hospital_name or 'site'}",
            "facts": {"medication": line.medication_name, "site": line.hospital_name, "on_hand": line.stock_quantity, "reorder_level": line.reorder_level,
                      "days_of_supply": line.days_of_supply, "forecast_30d_demand": f.predicted_30d_demand, "projected_shortfall": f.projected_shortfall,
                      "recommended_order": f.recommended_order_quantity, "estimated_cost_usd": f.estimated_procurement_cost,
                      "forecast_method": f.forecast.method_label},
        })
    return out


def _lab_candidates() -> List[Dict[str, Any]]:
    from backend.app.services import laboratory

    taken = actions.open_keys("lab_escalation", "lab_id")
    out = []
    for a in laboratory.list_critical_alerts(PageParams(limit=15), None).items:
        if a.lab_id in taken:
            continue
        out.append({
            "kind": "lab_escalation", "key": a.lab_id, "priority": 40,
            "payload": {"lab_id": a.lab_id, "patient_id": a.patient_id, "test_name": a.test_name, "context": {"test": a.test_name}},
            "summary": f"Escalate critical {a.test_name} for {a.patient_id}",
            "facts": {"patient_id": a.patient_id, "test": a.test_name, "value": a.test_value, "unit": a.unit, "reference_range": a.reference_range,
                      "result_date": a.test_date, "department": a.department_name, "policy": "Critical values require verbal physician notification (POL-LAB-001)"},
        })
    return out


# ---- 2. justify -----------------------------------------------------------------------------------

def _template(c: Dict[str, Any]) -> str:
    f = c["facts"]
    if c["kind"] == "follow_up":
        return (f"{f['patient_id']} (age {f['age']}) was diagnosed with stage {f['stage']} {f['cancer_type']} cancer on {f['diagnosed']} "
                f"({f['days_since_diagnosis']} days ago) and no treatment has started; the standard is first treatment within 30 days. "
                f"Approving creates a follow-up task to book treatment.")
    if c["kind"] == "purchase_order":
        return (f"{f['medication']} at {f['site']} has {f['on_hand']} units on hand (reorder level {f['reorder_level']}, {f['days_of_supply']} days of supply) "
                f"against a 30-day forecast of {f['forecast_30d_demand']}. Approving submits an order for {f['recommended_order']} units (≈${f['estimated_cost_usd']:,.0f}).")
    return (f"{f['patient_id']} had a critical {f['test']} of {f['value']} {f['unit'] or ''} (reference {f['reference_range']}) on {f['result_date']}; "
            f"POL-LAB-001 requires verbal physician notification. Approving creates an escalation task.")


def _justify(c: Dict[str, Any], use_ai: bool) -> str:
    if use_ai:
        try:
            text = providers.complete(JUSTIFY_SYSTEM, f"Proposed action: {c['summary']}\nFacts (JSON): {json.dumps(c['facts'], default=str)}")
            if text:
                return text[:600]
        except providers.ProviderError as e:
            logger.warning(f"Sweep justification fell back to template: {e}")
    return _template(c)


# ---- 3. run ---------------------------------------------------------------------------------------

def run_sweep(trigger: str = "manual") -> Dict[str, Any]:
    _ensure()
    run_id = uuid.uuid4().hex[:12]
    started = datetime.now()
    execute_query("INSERT INTO sweep_runs (run_id, trigger, started_at, status, found, proposed, skipped_duplicates, ai_used, suppressed) "
                  "VALUES (?, ?, ?, 'running', 0, 0, 0, FALSE, 0)", [run_id, trigger, started])
    try:
        found = _follow_up_candidates() + _stock_candidates() + _lab_candidates()
        # Learn from past decisions: drop kinds of proposals people keep rejecting (never safety-critical ones)
        suppressed = 0
        kept = []
        for c in found:
            c["history"] = learning.history_for(c["kind"], c["payload"].get("context", {}))
            if learning.should_suppress(c["kind"], c["history"], urgent=c.get("urgent", False)):
                suppressed += 1
                continue
            kept.append(c)
        # Highest priority first, but keep every kind represented within the cap
        by_kind: Dict[str, List[Dict[str, Any]]] = {}
        for c in sorted(kept, key=lambda x: -x["priority"]):
            by_kind.setdefault(c["kind"], []).append(c)
        chosen: List[Dict[str, Any]] = []
        while len(chosen) < MAX_PROPOSALS and any(by_kind.values()):
            for k in list(by_kind):
                if by_kind[k] and len(chosen) < MAX_PROPOSALS:
                    chosen.append(by_kind[k].pop(0))
        use_ai = providers.active_provider() in ("openai", "claude")
        made = []
        for c in chosen:
            note = c["history"].summary()
            reason = _justify(c, use_ai) + (f" {note}" if note else "")
            a = actions._propose_raw(c["kind"], "nexa-sweep@medinexus.org", "system", AGENT, f"sweep:{run_id}", c["payload"], reason, c["summary"])
            made.append({"action_id": a.action_id, "kind": c["kind"], "summary": c["summary"]})
        counts = {k: sum(1 for m in made if m["kind"] == k) for k in ("follow_up", "purchase_order", "lab_escalation")}
        execute_query("UPDATE sweep_runs SET finished_at = ?, status = 'succeeded', found = ?, proposed = ?, ai_used = ?, details = ?, suppressed = ? WHERE run_id = ?",
                      [datetime.now(), len(found), len(made), use_ai and bool(made), json.dumps(counts), suppressed, run_id])
        logger.info(f"Sweep {run_id} ({trigger}): {len(made)} proposals from {len(found)} candidates {counts}; {suppressed} suppressed by past decisions")
        return {"run_id": run_id, "found": len(found), "proposed": len(made), "by_kind": counts, "ai_used": use_ai and bool(made), "suppressed": suppressed}
    except Exception as e:
        execute_query("UPDATE sweep_runs SET finished_at = ?, status = 'failed', error = ? WHERE run_id = ?", [datetime.now(), str(e)[:500], run_id])
        raise


def _int(v: Any) -> int:
    """Nullable database integers (older runs predate some columns) come back as NA."""
    try:
        return 0 if v is None or v != v else int(v)
    except TypeError:  # pd.NA
        return 0


def _ts(v: Any) -> Optional[str]:
    try:
        return None if v is None or v != v else str(v)[:19].replace(" ", "T")
    except TypeError:
        return None


def recent_runs(limit: int = 5) -> List[Dict[str, Any]]:
    _ensure()
    df = query_df_strict("SELECT * FROM sweep_runs ORDER BY started_at DESC LIMIT ?", [int(limit)])
    out = []
    for r in df.itertuples():
        out.append({"run_id": r.run_id, "trigger": r.trigger, "started_at": _ts(r.started_at), "finished_at": _ts(r.finished_at),
                    "status": r.status, "found": _int(r.found), "proposed": _int(r.proposed), "ai_used": bool(r.ai_used) if isinstance(r.ai_used, (bool, int)) else False,
                    "by_kind": json.loads(r.details) if isinstance(r.details, str) and r.details else {},
                    "error": r.error if isinstance(r.error, str) else None, "suppressed": _int(getattr(r, "suppressed", 0))})
    return out


# ---- scheduler ------------------------------------------------------------------------------------

def _ran_today() -> bool:
    _ensure()
    df = query_df_strict("SELECT COUNT(*) AS n FROM sweep_runs WHERE trigger = 'schedule' AND status = 'succeeded' AND CAST(started_at AS DATE) = ?", [date.today()])
    return int(df.iloc[0]["n"]) > 0


def next_run_at(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now()
    hh, mm = (int(x) for x in SWEEP_TIME.split(":"))
    today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return today if now < today else today + timedelta(days=1)


def start_scheduler(stop: threading.Event) -> Optional[threading.Thread]:
    """Daily sweep in a background thread. Disabled with NEXA_SWEEP_ENABLED=0 (tests)."""
    if os.getenv("NEXA_SWEEP_ENABLED", "1") == "0":
        return None

    def loop() -> None:
        from backend.app.jobs import runner

        while not stop.wait(60):
            try:
                hh, mm = (int(x) for x in SWEEP_TIME.split(":"))
                now = datetime.now()
                due = now.hour > hh or (now.hour == hh and now.minute >= mm)
                if due and not _ran_today() and runner.active_job("nexa_sweep") is None:
                    runner.submit("nexa_sweep", "nexa-sweep@medinexus.org", lambda ctx: run_sweep("schedule"))
            except Exception as e:  # never let the scheduler thread die
                logger.warning(f"Sweep scheduler check failed: {e}")
                time.sleep(5)

    t = threading.Thread(target=loop, name="nexa-sweep-scheduler", daemon=True)
    t.start()
    return t
