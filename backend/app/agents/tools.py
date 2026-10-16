"""
Tool registry for the Nexa agents.

Each tool wraps an existing platform service (the same code the dashboards use), returns plain
JSON-able data, and never exposes patient names (pseudonymous IDs only). Tools are grouped and each
agent sees only its groups, which mirror the role-based page access.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.app.core.access import can_access
from backend.app.core.errors import APIError
from backend.app.core.pagination import PageParams
from backend.app.core.users import UserRecord
from src.utils.database import query_df_strict

MAX_RESULT_CHARS = 6_000  # keeps each tool result small (token cost)


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    group: str  # insight | care | pharmalab | common
    page: Optional[str] = None  # page permission the caller must hold
    proposes: bool = False
    required: List[str] = field(default_factory=list)

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": self.parameters, "required": self.required, "additionalProperties": False}


def _dump(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, list):
        return [_dump(x) for x in v]
    return v


def _strip_names(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Agents work with pseudonymous patient IDs only."""
    return [{k: v for k, v in r.items() if k not in ("name", "patient_name", "city")} for r in rows]


# ---- common -------------------------------------------------------------------------------------

def remember(user: UserRecord, text: str) -> Dict[str, Any]:
    from backend.app.agents import memory

    m = memory.add(user, text, source="chat")
    return {"saved": m["text"], "memory_id": m["memory_id"],
            "note": "Saved to this user's long-term memory. They can see and delete it under 'What Nexa remembers'."}


def search_policies(user: UserRecord, query: str) -> Dict[str, Any]:
    from src.rag.retriever import retrieve_context

    hits = retrieve_context(query, top_k=3)
    return {
        "note": "Policy and guideline excerpts found by hybrid search (meaning + keywords). Quote only what is here and cite as "
                "[Policy: <policy_id> <section>]. An empty list means the library has nothing on this.",
        "results": [{"document": h["title"], "policy_id": h["policy_id"], "section": h["section"], "file": h["filename"],
                     "relevance": h["score"], "text": h["text"][:1500]} for h in hits],
    }


# ---- insight (operations analyst) -----------------------------------------------------------------

def get_network_kpis(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    return _dump(executive.get_kpis())


OUTCOME_DIMENSIONS = {
    "cancer_type": "cancer_type",
    "stage": "'Stage ' || cancer_stage",
    "age_band": "CASE WHEN age_at_diagnosis < 50 THEN 'under 50' WHEN age_at_diagnosis < 65 THEN '50-64' WHEN age_at_diagnosis < 75 THEN '65-74' ELSE '75+' END",
    "treatment_status": "treatment_status",
}


def get_outcomes_by(user: UserRecord, dimension: str, min_patients: int = 20, limit: int = 15) -> Dict[str, Any]:
    if dimension not in OUTCOME_DIMENSIONS:
        raise ValueError(f"dimension must be one of {sorted(OUTCOME_DIMENSIONS)}")
    df = query_df_strict(f"""
        SELECT {OUTCOME_DIMENSIONS[dimension]} AS grp, COUNT(*) AS patients, SUM(is_deceased) AS deaths,
               ROUND(AVG(is_deceased) * 100, 1) AS died_pct,
               median(days_to_treatment) FILTER (WHERE days_to_treatment >= 0) AS median_days_to_treatment,
               COUNT(*) FILTER (WHERE treatment_status = 'In treatment') AS in_treatment
        FROM gold_oncology_patients GROUP BY 1 HAVING COUNT(*) >= ? ORDER BY died_pct DESC, patients DESC LIMIT ?
    """, [max(1, int(min_patients)), max(1, min(int(limit), 50))])
    return {
        "dimension": dimension,
        "definition": "Crude share of patients who have died since diagnosis (follow-up time differs between patients; "
                      "use get_survival_by_type for Kaplan-Meier survival, which accounts for that).",
        "reliability_note": "died_pct is an observed share; ci95 is its 95% Wilson range. Small groups have wide ranges.",
        "rows": [{"group": str(r.grp), "patients": int(r.patients), "deaths": int(r.deaths or 0), "died_pct": float(r.died_pct or 0),
                  "ci95_pct": _wilson(int(r.deaths or 0), int(r.patients)),
                  "median_days_to_treatment": None if r.median_days_to_treatment != r.median_days_to_treatment else float(r.median_days_to_treatment),
                  "in_treatment": int(r.in_treatment)} for r in df.itertuples()],
    }


def _wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    """95% Wilson score interval for a proportion, in percent."""
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return [round(max(0.0, centre - half) * 100, 2), round(min(1.0, centre + half) * 100, 2)]


def get_diagnoses_trend(user: UserRecord, months: int = 12) -> Dict[str, Any]:
    from backend.app.services import executive

    rows = executive.get_diagnoses_trend(max(6, min(int(months), 120)))
    return {"unit": "new cancer diagnoses per month (value) and deaths per month (secondary)", "rows": _dump(rows)}


def get_survival_by_type(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    s = executive.get_survival()
    return {"method": s.note, "rows": _dump(s.by_type)}


def get_cost_by_cancer_type(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    return {"currency": "USD", "basis": "recorded surgical claims, visits and medicines per patient (synthetic costs)", "rows": _dump(executive.get_cost_by_type())}


def get_treatment_forecast(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    f = executive.get_forecasts()
    return {"horizon": "next 7 days, average sessions per day across the network", "rows": _dump(f.treatment),
            "method": f.treatment_forecast.method_label}


def list_hospitals_by_access_pressure(user: UserRecord, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import command

    return {"data_source": "SIMULATED operations data", "rows": _dump(command.list_hospitals()[: max(1, min(int(limit), 91))])}


def run_capacity_what_if(user: UserRecord, extra_visits_per_physician: float = 0, extra_physicians: int = 0, demand_change_pct: float = 0,
                         hospital_id: Optional[str] = None, period: str = "last_365") -> Dict[str, Any]:
    from backend.app.schemas.command import WhatIfIn
    from backend.app.services import command

    r = command.run_what_if(WhatIfIn(hospital_id=hospital_id, period=period, extra_visits_per_physician=extra_visits_per_physician,
                                     extra_physicians=extra_physicians, demand_change_pct=demand_change_pct))
    out = r.model_dump(exclude={"daily"})
    out["data_source"] = "SIMULATED operations data"
    return out


def list_model_scores(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import command

    return {"rows": _dump(command.list_model_monitor())}


# ---- care (clinical) ------------------------------------------------------------------------------

def get_tumour_board(user: UserRecord, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import clinical

    rows = _strip_names(_dump(clinical.get_worklist(max(1, min(int(limit), 25)))))
    return {"basis": "living cancer patients ranked by predicted 12-month mortality risk (served method: see list_model_scores)", "rows": rows}


def get_patient_summary(user: UserRecord, patient_id: str) -> Dict[str, Any]:
    from backend.app.services import clinical

    p = clinical.get_patient_360(patient_id, user)  # audited as a PATIENT_VIEW
    out = {k: v for k, v in p.model_dump().items() if k not in ("name", "city")}
    out["care_gaps"] = _strip_names(out.get("care_gaps", []))
    try:
        out["risk"] = clinical.get_patient_risk(patient_id, user).model_dump()
    except APIError:
        out["risk"] = None
    return out


def get_care_gap_summary(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import clinical

    return {"rows": _dump(clinical.get_care_gap_summary())}


def list_care_gaps(user: UserRecord, gap: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import clinical

    page = clinical.list_care_gaps(PageParams(limit=max(1, min(int(limit), 50))), gap)
    return {"rows": _strip_names(_dump(page.items))}


# ---- pharmacy & lab -------------------------------------------------------------------------------

def get_pharmacy_kpis(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import pharmacy

    return _dump(pharmacy.get_kpis())


def find_stock(user: UserRecord, search: Optional[str] = None, risk: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import pharmacy

    if risk and risk not in ("High Risk", "Moderate Risk", "Safe"):
        raise ValueError("risk must be 'High Risk', 'Moderate Risk' or 'Safe'")
    page = pharmacy.list_stock(PageParams(limit=max(1, min(int(limit), 50))), risk, search)
    return {"rows": _dump(page.items), "note": "Stock lines are per site × medication; an empty list means no match for that search."}


def get_stock_forecast(user: UserRecord, inventory_id: str) -> Dict[str, Any]:
    from backend.app.services import pharmacy

    return _dump(pharmacy.get_demand_forecast(inventory_id))


def get_drug_class_outlook(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import pharmacy

    out = _dump(pharmacy.get_class_outlook())
    out["data_source"] = "SIMULATED operations data"
    return out


def get_lab_kpis(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import laboratory

    return _dump(laboratory.get_kpis())


def list_critical_lab_alerts(user: UserRecord, category: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import laboratory

    page = laboratory.list_critical_alerts(PageParams(limit=max(1, min(int(limit), 50))), category)
    return {"rows": _dump(page.items)}


# ---- proposals (human approval required) ---------------------------------------------------------

def propose_purchase_order(user: UserRecord, inventory_id: str, quantity: int, reason: str, _ctx: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.agents import actions
    from backend.app.services import pharmacy

    from backend.app.agents import learning

    line = pharmacy._stock_line(inventory_id)  # 404s on an unknown line
    context = {"site": str(line.get("hospital_name") or ""), "medication": str(line["medication_name"])}
    history = learning.history_for("purchase_order", context).summary()
    a = actions.propose(
        kind="purchase_order", requested_by=user, agent=_ctx["agent"], session_id=_ctx.get("session_id"),
        payload={"inventory_id": inventory_id, "quantity": int(quantity), "context": context}, reason=reason + (f" {history}" if history else ""),
        summary=f"Purchase order: {int(quantity)} units of {line['medication_name']} for {line.get('hospital_name') or 'site'}",
    )
    return {"status": "pending_approval", "action_id": a.action_id, "summary": a.summary, "past_decisions": history or "No similar past decisions.",
            "note": "Nothing has been ordered. A pharmacist or administrator must approve this in the approval inbox."}


def propose_follow_up(user: UserRecord, patient_id: str, reason: str, due_in_days: int = 7, _ctx: Dict[str, Any] = None) -> Dict[str, Any]:
    from backend.app.agents import actions
    from backend.app.services import clinical

    from backend.app.agents import learning

    clinical._patient_row(patient_id)  # 404s on an unknown patient
    scores = clinical._scored_living().set_index("patient_id")["mortality_risk"]
    context = {"risk_band": learning.risk_band(float(scores[patient_id]) * 100 if patient_id in scores.index else None)}
    history = learning.history_for("follow_up", context).summary()
    a = actions.propose(
        kind="follow_up", requested_by=user, agent=(_ctx or {}).get("agent", ""), session_id=(_ctx or {}).get("session_id"),
        payload={"patient_id": patient_id, "due_in_days": max(1, min(int(due_in_days), 90)), "context": context},
        reason=reason + (f" {history}" if history else ""),
        summary=f"Follow-up for {patient_id} within {max(1, min(int(due_in_days), 90))} days",
    )
    return {"status": "pending_approval", "action_id": a.action_id, "summary": a.summary, "past_decisions": history or "No similar past decisions.",
            "note": "No task has been created yet. A clinician or administrator must approve this in the approval inbox."}


def _s(desc: str, **extra: Any) -> Dict[str, Any]:
    return {"type": "string", "description": desc, **extra}


def _i(desc: str, **extra: Any) -> Dict[str, Any]:
    return {"type": "integer", "description": desc, **extra}


def _n(desc: str, **extra: Any) -> Dict[str, Any]:
    return {"type": "number", "description": desc, **extra}


TOOLS: List[Tool] = [
    Tool("search_policies", "Search hospital policies and clinical guidelines (discharge, follow-up, medication storage, lab safety, privacy, appointments). Returns document excerpts to quote.",
         {"query": _s("What to look for, in plain words")}, search_policies, "common", required=["query"]),
    Tool("remember", "Save a preference or standing instruction to the user's long-term memory (e.g. 'I manage Site X', 'show money in thousands'). "
                     "Call ONLY when the user explicitly asks you to remember something. Never store patient data; patient IDs and personal details are refused.",
         {"text": _s("What to remember, as one short sentence")}, remember, "common", required=["text"]),

    Tool("get_network_kpis", "Oncology network KPIs from Gold: cancer patients, living, new diagnoses in 12 months, 5-year survival, median days from diagnosis to first treatment, treatment sessions in 30 days, recorded cost of care, hospitals, data-through date.",
         {}, get_network_kpis, "insight", page="executive"),
    Tool("get_outcomes_by", "Patients, deaths, crude share died, median days to treatment and patients in treatment, grouped by cancer_type, stage, age_band (at diagnosis) or treatment_status.",
         {"dimension": _s("Grouping", enum=sorted(OUTCOME_DIMENSIONS)),
          "min_patients": _i("Hide groups with fewer patients than this", minimum=1, maximum=10000),
          "limit": _i("Max rows", minimum=1, maximum=50)},
         get_outcomes_by, "insight", page="executive", required=["dimension"]),
    Tool("get_diagnoses_trend", "New cancer diagnoses and deaths per month for the last N months of data.",
         {"months": _i("Months of history (6-120)", minimum=6, maximum=120)}, get_diagnoses_trend, "insight", page="executive"),
    Tool("get_survival_by_type", "Kaplan-Meier survival at 1, 3 and 5 years per cancer type, with stage I and stage IV 5-year survival.", {}, get_survival_by_type, "insight", page="executive"),
    Tool("get_cost_by_cancer_type", "Recorded cost of care (USD) per cancer type: total and per patient.", {}, get_cost_by_cancer_type, "insight", page="executive"),
    Tool("get_treatment_forecast", "Next-7-day forecast of infusion-chair (chemo / immuno / targeted) and radiation sessions per day.", {}, get_treatment_forecast, "insight", page="executive"),
    Tool("list_hospitals_by_access_pressure", "Hospitals ranked by outpatient access pressure (share of demand served, wait days). SIMULATED operations data.",
         {"limit": _i("Max rows", minimum=1, maximum=91)}, list_hospitals_by_access_pressure, "insight", page="command"),
    Tool("run_capacity_what_if", "Replay a year of outpatient demand with changed staffing or demand and return waiting list, wait, lost patients, revenue and staffing cost vs baseline. SIMULATED operations data.",
         {"extra_visits_per_physician": _n("Extra visits per doctor per day (0-15)", minimum=0, maximum=15),
          "extra_physicians": _i("Extra physicians per hospital (0-50)", minimum=0, maximum=50),
          "demand_change_pct": _n("Demand change in percent (-50 to 100)", minimum=-50, maximum=100),
          "hospital_id": _s("One hospital id (from list_hospitals_by_access_pressure); omit for the whole network"),
          "period": _s("Replay window", enum=["last_365", "last_90"])},
         run_capacity_what_if, "insight", page="command"),
    Tool("list_model_scores", "Every active ML model with its held-out score vs a baseline, data source, version and health.", {}, list_model_scores, "insight", page="command"),

    Tool("get_tumour_board", "Tumour-board worklist: living cancer patients ranked by predicted 12-month mortality risk, with cancer type, stage, treatment status, regimen, tumour-marker trend and drivers. Pseudonymous patient IDs only.",
         {"limit": _i("Max patients (1-25)", minimum=1, maximum=25)}, get_tumour_board, "care", page="doctor"),
    Tool("get_patient_summary", "Patient 360 for one patient ID (e.g. P_04436): cancer type, stage, diagnosis date, treatment pathway (surgery, chemo/immunotherapy cycles, radiation), tumour marker, labs, comorbidities, care gaps, 12-month mortality risk and care plan. Every call is audited.",
         {"patient_id": _s("Patient ID like P_04436", pattern=r"^P_\d{1,6}$")}, get_patient_summary, "care", page="doctor", required=["patient_id"]),
    Tool("get_care_gap_summary", "Count of patients per oncology care gap (treatment not started within 30 days, cycle without a blood count, rising tumour marker, survivorship follow-up overdue, high risk without palliative review).", {}, get_care_gap_summary, "care", page="doctor"),
    Tool("list_care_gaps", "Patients with an oncology care gap, optionally one gap type.",
         {"gap": _s("Gap code", enum=["treatment_delay", "chemo_no_cbc", "rising_marker", "follow_up_overdue", "goals_of_care"]), "limit": _i("Max rows", minimum=1, maximum=50)},
         list_care_gaps, "care", page="doctor"),
    Tool("propose_follow_up", "PROPOSE a follow-up appointment/call for a patient. Creates a pending item in the approval inbox; nothing happens until a clinician approves.",
         {"patient_id": _s("Patient ID like P_04436", pattern=r"^P_\d{1,6}$"), "reason": _s("Why, citing the evidence"), "due_in_days": _i("Within N days (1-90)", minimum=1, maximum=90)},
         propose_follow_up, "care", page="doctor", proposes=True, required=["patient_id", "reason"]),

    Tool("get_pharmacy_kpis", "Pharmacy KPIs: stock lines, high/moderate stock-out risk lines, units dispensed (180 days), active prescriptions.", {}, get_pharmacy_kpis, "pharmalab", page="pharmacy"),
    Tool("find_stock", "Find stock lines by medication name and/or stock-out risk; returns on-hand, reorder level, days of supply, inventory_id.",
         {"search": _s("Medication name fragment, e.g. insulin"), "risk": _s("Risk filter", enum=["High Risk", "Moderate Risk", "Safe"]), "limit": _i("Max rows", minimum=1, maximum=50)},
         find_stock, "pharmalab", page="pharmacy"),
    Tool("get_stock_forecast", "30-day demand forecast, shortfall and recommended order for one stock line (inventory_id from find_stock).",
         {"inventory_id": _s("inventory_id from find_stock")}, get_stock_forecast, "pharmalab", page="pharmacy", required=["inventory_id"]),
    Tool("get_drug_class_outlook", "Network demand outlook per drug class for the next 7 days. SIMULATED operations data.", {}, get_drug_class_outlook, "pharmalab", page="pharmacy"),
    Tool("get_lab_kpis", "Laboratory KPIs: total, abnormal and critical results, tests in the last 30 days.", {}, get_lab_kpis, "pharmalab", page="laboratory"),
    Tool("list_critical_lab_alerts", "Most recent critical lab values (pseudonymous patient IDs), optionally one discipline.",
         {"category": _s("Lab discipline, e.g. Chemistry"), "limit": _i("Max rows", minimum=1, maximum=50)}, list_critical_lab_alerts, "pharmalab", page="laboratory"),
    Tool("propose_purchase_order", "PROPOSE a purchase order for a stock line. Creates a pending item in the approval inbox; nothing is ordered until a pharmacist approves.",
         {"inventory_id": _s("inventory_id from find_stock"), "quantity": _i("Units to order (1-100000)", minimum=1, maximum=100000), "reason": _s("Why, citing the forecast or stock level")},
         propose_purchase_order, "pharmalab", page="pharmacy", proposes=True, required=["inventory_id", "quantity", "reason"]),
]

AGENT_GROUPS = {
    "medicare": {"common", "care"},
    "pharmalab": {"common", "pharmalab"},
    "healthanalyst": {"common", "insight"},
    "ops": {"common", "insight", "care", "pharmalab"},
}
BY_NAME = {t.name: t for t in TOOLS}


def tools_for(agent: str, user: UserRecord) -> List[Tool]:
    groups = AGENT_GROUPS.get(agent, {"common"})
    return [t for t in TOOLS if t.group in groups and (t.page is None or can_access(user.role, t.page))]


def run_tool(name: str, args: Dict[str, Any], user: UserRecord, ctx: Dict[str, Any], allowed: List[Tool]) -> Dict[str, Any]:
    """Execute one tool call; errors come back as data so the model can recover or say it cannot answer."""
    import json

    tool = next((t for t in allowed if t.name == name), None)
    if tool is None:
        return {"ok": False, "error": f"Tool '{name}' is not available to this assistant."}
    args = dict(args or {})
    unknown = set(args) - set(tool.parameters)
    if unknown:
        return {"ok": False, "error": f"Unknown arguments: {', '.join(sorted(unknown))}"}
    missing = [r for r in tool.required if args.get(r) in (None, "")]
    if missing:
        return {"ok": False, "error": f"Missing required arguments: {', '.join(missing)}"}
    try:
        data = tool.handler(user, **args, _ctx=ctx) if tool.proposes else tool.handler(user, **args)
    except APIError as e:
        return {"ok": False, "error": e.detail}
    except (ValueError, TypeError, KeyError) as e:
        return {"ok": False, "error": str(e)}
    text = json.dumps(data, default=str)
    if len(text) > MAX_RESULT_CHARS:
        return {"ok": True, "truncated": True, "data": text[:MAX_RESULT_CHARS]}
    return {"ok": True, "data": data}
