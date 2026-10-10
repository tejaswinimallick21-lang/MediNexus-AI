"""
Nexa agent engine: picks the provider, scopes tools to the agent and the user's role, runs the
tool loop, and returns a structured reply with the tool trace and any proposed actions.

Without an LLM key (or when the LLM is unreachable) a rules engine answers only questions it can
map to one tool, and otherwise says what it can answer; it never fills gaps with invented text.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.app.agents import memory, providers
from backend.app.agents.tools import BY_NAME, Tool, run_tool, tools_for
from backend.app.core.users import UserRecord
from src.security.audit import log_audit_event

AGENT_SCOPE = {
    "medicare": "You are Nexa Care, the clinical assistant for healthcare professionals: readmission risk, Patient 360, care gaps, follow-ups and clinical guidelines.",
    "pharmalab": "You are Nexa Care · Lab & Pharmacy: stock-out risk, demand forecasts, purchase orders, critical lab values and lab/pharmacy policy.",
    "healthanalyst": "You are Nexa Insight, the operations analyst assistant: admissions, readmissions, revenue, capacity, what-if simulations, readmission economics and model quality.",
    "ops": "You are Nexa Ops, the administrator's assistant with oversight of every workspace: operations, clinical, pharmacy, laboratory and model quality.",
}

RULES = """
How you work (these rules are not negotiable):
1. Every number, name, ranking or claim about this hospital network must come from a tool result in this conversation. If no tool gives the answer, say plainly that you do not have that data and say what you can answer instead. Never estimate, extrapolate or invent figures, trends, percentages, guidelines or patient details.
2. Call tools before answering factual questions. Prefer the most specific tool (e.g. get_readmissions_by with dimension=hospital for "which hospital…"). If a tool returns an error or an empty list, report that honestly.
3. After each fact, name its source in brackets, e.g. [Gold admissions], [Policy: Discharge policy], [Model registry], [SIMULATED operations data]. Always label simulated data as simulated.
4. Patients are identified only by pseudonymous IDs like P_04436. Never ask for or reveal names.
5. Actions: you cannot perform actions. You may only PROPOSE them with a propose_* tool when the user asks for one or the evidence clearly supports it, and you must say it is pending human approval in the approval inbox. Never claim something was ordered, booked or done.
6. You provide decision support, not diagnosis or treatment. For clinical questions, cite the guideline excerpt and recommend clinician review.
7. Questions outside the hospital platform (weather, news, general trivia, coding) are out of scope: decline in one sentence.
8. Observed rates (counts from the data) and model predictions are different things. To judge how reliable an observed rate is, use its sample size and ci95 range, not model accuracy metrics.
9. Be concise: a direct answer first, then up to 5 bullet points of evidence. Use plain language; explain any metric you mention (e.g. "AUC 0.80 means the model ranks a readmitted patient above a non-readmitted one 80% of the time").
""".strip()


def system_prompt(agent: str, memories: str = "") -> str:
    prompt = f"{AGENT_SCOPE.get(agent, AGENT_SCOPE['ops'])}\n\nYou work inside MediNexus AI, a hospital-network platform. Currency is USD. Data comes from the Gold lakehouse (Synthea clinical data), simulated operations tables (clearly labelled), the model registry and the hospital policy library.\n\n{RULES}"
    return f"{prompt}\n\n{memories}" if memories else prompt


# ---- rules engine (no LLM) ------------------------------------------------------------------------

REMEMBER = re.compile(r"^\s*(please\s+)?(remember|keep in mind)\b", re.I)
POLICY_WORDS = re.compile(r"guideline|policy|protocol|procedure|standard|temperature|storage|handling|privacy|how should|what does .* say", re.I)
PATIENT_ID = re.compile(r"\bP_\d{1,6}\b", re.I)


def _route(agent: str, message: str, allowed: Dict[str, Tool]) -> Optional[Tuple[str, Dict[str, Any]]]:
    m = message.lower()
    if REMEMBER.search(message) and "remember" in allowed:
        return "remember", {"text": message}
    pid = PATIENT_ID.search(message)
    if pid and "get_patient_summary" in allowed:
        return "get_patient_summary", {"patient_id": pid.group(0).upper()}
    if POLICY_WORDS.search(m) and "search_policies" in allowed:
        return "search_policies", {"query": message}
    if "readmi" in m and "get_readmissions_by" in allowed:
        for word, dim in (("hospital", "hospital"), ("department", "department"), ("ward", "department"), ("reason", "admission_reason"),
                          ("diagnos", "admission_reason"), ("age", "age_band"), ("type", "admission_type"), ("emergency", "admission_type")):
            if word in m:
                return "get_readmissions_by", {"dimension": dim}
        if "get_network_kpis" in allowed:
            return "get_network_kpis", {}
    if re.search(r"high(est)?[- ]risk|risk(iest)? patients|huddle", m) and "get_highest_risk_discharges" in allowed:
        return "get_highest_risk_discharges", {"limit": 10}
    if "care gap" in m and "get_care_gap_summary" in allowed:
        return "get_care_gap_summary", {}
    if re.search(r"replenish|stock[- ]?out|reorder|low stock|running out", m) and "find_stock" in allowed:
        return "find_stock", {"risk": "High Risk", "limit": 10}
    med = re.search(r"(?:units of|stock of|supply of|inventory of|much|many)\s+([a-z][a-z0-9 \-]{2,40}?)(?:\s+(?:do|in|left|we|are|is)\b|\?|$)", m)
    if med and "find_stock" in allowed:
        return "find_stock", {"search": med.group(1).strip(), "limit": 10}
    if re.search(r"critical|escalat|lab alert", m) and "list_critical_lab_alerts" in allowed:
        return "list_critical_lab_alerts", {"limit": 10}
    if re.search(r"drug class|class outlook", m) and "get_drug_class_outlook" in allowed:
        return "get_drug_class_outlook", {}
    if re.search(r"\blab\b|laborator", m) and "get_lab_kpis" in allowed:
        return "get_lab_kpis", {}
    if re.search(r"revenue|billing|billed", m) and "get_revenue_by_department" in allowed:
        return "get_revenue_by_department", {}
    if re.search(r"capacity|surge|occupancy|\bbeds?\b", m) and "get_capacity_plan" in allowed:
        return "get_capacity_plan", {}
    if re.search(r"trend|per month|monthly", m) and "get_admissions_trend" in allowed:
        return "get_admissions_trend", {"months": 12}
    if re.search(r"model|accuracy|auc", m) and "list_model_scores" in allowed:
        return "list_model_scores", {}
    if re.search(r"access pressure|waiting|wait time", m) and "list_hospitals_by_access_pressure" in allowed:
        return "list_hospitals_by_access_pressure", {"limit": 10}
    if re.search(r"kpi|overview|admission|admitted|patients", m) and "get_network_kpis" in allowed:
        return "get_network_kpis", {}
    if re.search(r"pharmacy|prescription|dispens", m) and "get_pharmacy_kpis" in allowed:
        return "get_pharmacy_kpis", {}
    return None


LABELS = {
    "search_policies": ("Policy library", None),
    "remember": ("Saved to long-term memory", None),
    "get_network_kpis": ("Network KPIs [Gold]", None),
    "get_readmissions_by": ("Unplanned 30-day readmission rates, highest first [Gold admissions]", ["group", "rate_pct", "unplanned_readmissions", "admissions"]),
    "get_admissions_trend": ("Monthly admissions [Gold]", ["period", "value", "secondary"]),
    "get_revenue_by_department": ("Billed revenue by department, USD [Gold billing]", ["department", "revenue", "admissions"]),
    "get_capacity_plan": ("Capacity outlook", None),
    "list_model_scores": ("Model registry", ["label", "primary_metric", "baseline", "verdict", "serving"]),
    "list_hospitals_by_access_pressure": ("Outpatient access pressure [SIMULATED operations data]", ["hospital_name", "served_pct", "avg_wait_days", "avg_daily_demand"]),
    "get_highest_risk_discharges": ("Highest-risk recent discharges [readmission model]",
                                    ["patient_id", "readmission_probability_pct", "risk_level", "age", "admission_reason", "discharge_date", "has_follow_up"]),
    "get_patient_summary": ("Patient 360 [Gold]", None),
    "get_care_gap_summary": ("Care gaps", ["label", "patients", "guideline"]),
    "list_care_gaps": ("Patients with care gaps", ["patient_id", "label", "detail", "last_done"]),
    "get_pharmacy_kpis": ("Pharmacy KPIs", None),
    "find_stock": ("Stock lines [pharmacy inventory]", ["medication_name", "hospital_name", "stock_quantity", "reorder_level", "days_of_supply", "stockout_risk", "inventory_id"]),
    "get_stock_forecast": ("30-day demand forecast", None),
    "get_drug_class_outlook": ("Drug-class outlook [SIMULATED operations data]", ["drug_class", "forecast_daily_units", "change_pct"]),
    "get_lab_kpis": ("Laboratory KPIs", None),
    "list_critical_lab_alerts": ("Critical lab values", ["patient_id", "test_name", "test_value", "unit", "reference_range", "test_date"]),
}


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _facts(name: str, data: Any) -> List[str]:
    """Plain restatement of a tool result; no interpretation beyond the numbers."""
    if not isinstance(data, dict):
        return [str(data)[:400]]
    if name == "search_policies":
        out = []
        for r in data.get("results", []):
            body = re.sub(r"\[DEMO[^\]]*\]|DOCUMENT TITLE:[^\n]*", "", r["text"]).strip()
            out.append(f"{r['document']} ({r.get('policy_id', '')}) · {r.get('section', '')}: {body[:500]}…")
        return out or ["No policy excerpt matched that question."]
    if name == "remember":
        return [f"\"{data.get('saved', '')}\"", "You can see and delete it under 'What Nexa remembers'."]
    if "rows" in data or "items" in data:
        rows = data.get("rows") if "rows" in data else data.get("items")
        if not rows:
            return ["No matching records."]
        prefer = LABELS.get(name, (None, None))[1]
        out = []
        for r in rows[:8]:
            if isinstance(r, dict):
                keys = [k for k in (prefer or r.keys()) if k in r and r[k] is not None and not isinstance(r[k], (list, dict))][:7]
                out.append(" · ".join(f"{k.replace('_', ' ')}: {_fmt(r[k])}" for k in keys))
        return out
    keep = [(k, v) for k, v in data.items() if not isinstance(v, (list, dict)) and v is not None][:10]
    return [f"{k.replace('_', ' ')}: {_fmt(v)}" for k, v in keep]


def _capabilities(allowed: Dict[str, Tool]) -> str:
    examples = {
        "get_readmissions_by": "readmission rates by hospital, department, reason or age band",
        "get_network_kpis": "network KPIs (admissions, readmission rate, length of stay, revenue)",
        "get_highest_risk_discharges": "the highest-risk recent discharges",
        "get_patient_summary": "a patient summary by ID (e.g. P_04436)",
        "find_stock": "stock levels for a medicine or lines at stock-out risk",
        "list_critical_lab_alerts": "recent critical lab values",
        "search_policies": "what a hospital policy or guideline says",
        "get_capacity_plan": "the capacity and surge outlook",
    }
    items = [v for k, v in examples.items() if k in allowed]
    return "I can answer questions about: " + "; ".join(items) + "."


def _rules_answer(agent: str, message: str, user: UserRecord, allowed: Dict[str, Tool], execute) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    route = _route(agent, message, allowed)
    if route is None:
        return ("I can't answer that reliably without the AI engine, and I won't guess. " + _capabilities(allowed)), [], []
    name, args = route
    result = execute(name, args)
    trace = [{"name": name, "args": args, "ok": bool(result.get("ok")), "error": result.get("error")}]
    if not result.get("ok"):
        return f"I couldn't do that: {result.get('error')}", [], trace
    facts = _facts(name, result.get("data"))
    label = LABELS.get(name, (BY_NAME[name].description.split(".")[0], None))[0]
    return f"{label}. Shown as returned by the platform (rules engine, no AI interpretation):", facts, trace


# ---- entry point ----------------------------------------------------------------------------------

def run(agent: str, message: str, user: UserRecord, history: Optional[List[Tuple[str, str]]] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
    started = time.perf_counter()
    tools = tools_for(agent, user)
    allowed = {t.name: t for t in tools}
    proposed: List[Dict[str, Any]] = []
    sources: List[str] = []

    def execute(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        r = run_tool(name, args, user, {"agent": agent, "session_id": session_id}, tools)
        data = r.get("data") if isinstance(r.get("data"), dict) else {}
        if r.get("ok") and data.get("action_id"):
            proposed.append({"action_id": data["action_id"], "summary": data.get("summary", ""), "status": "pending"})
        if r.get("ok") and name == "search_policies":
            sources.extend(f"Policy: {x['document']} ({x.get('policy_id') or x['file']}) · {x.get('section', '')}" for x in data.get("results", []))
        return r

    provider = providers.active_provider()
    notes = ""
    facts: List[str] = []
    if provider in ("claude", "openai"):
        try:
            runner = providers.run_claude if provider == "claude" else providers.run_openai
            answer, trace = runner(system_prompt(agent, memory.prompt_block(user)), history or [], message, tools, execute)
            engine = providers.provider_label()
        except providers.ProviderError as e:
            notes = f"AI engine unavailable ({e}); answered by the rules engine."
            answer, facts, trace = _rules_answer(agent, message, user, allowed, execute)
            engine = "Rules engine (fallback)"
    else:
        answer, facts, trace = _rules_answer(agent, message, user, allowed, execute)
        engine = providers.provider_label()

    evidence = [f"Tool {t['name']}" + ("" if t["ok"] else f" (failed: {t['error']})") for t in trace] + sources
    latency = round((time.perf_counter() - started) * 1000, 1)
    # Audit what the agent did, not what was asked (questions can contain patient details)
    log_audit_event(username=user.email, role=user.role, action="AGENT_QUERY", resource=agent, status="FALLBACK" if notes else "SUCCESS",
                    details=json.dumps({"engine": engine, "tools": [t["name"] for t in trace], "failed_tools": sum(not t["ok"] for t in trace),
                                        "proposals": len(proposed), "latency_ms": latency}))
    return {
        "agent": agent, "answer": answer or "I don't have an answer for that.", "facts": facts, "predictions": [], "recommendations": [],
        "evidence": list(dict.fromkeys(evidence)), "notes": notes, "latency_ms": latency,
        "engine": engine, "tool_calls": trace, "proposed_actions": proposed,
    }
