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

def search_policies(user: UserRecord, query: str) -> Dict[str, Any]:
    from src.rag.retriever import retrieve_context

    hits = retrieve_context(query, top_k=3)
    return {
        "note": "Excerpts from hospital policy and guideline documents (keyword search). Quote only what is here.",
        "results": [{"document": h["title"], "file": h["filename"], "relevance": h["score"], "text": h["text"][:1500]} for h in hits],
    }


# ---- insight (operations analyst) -----------------------------------------------------------------

def get_network_kpis(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    return _dump(executive.get_kpis())


READMISSION_DIMENSIONS = {
    "hospital": "hospital_name",
    "department": "department_name",
    "admission_type": "admission_type",
    "admission_reason": "admission_reason",
    "age_band": "CASE WHEN age < 18 THEN '0-17' WHEN age < 40 THEN '18-39' WHEN age < 65 THEN '40-64' WHEN age < 80 THEN '65-79' ELSE '80+' END",
}


def get_readmissions_by(user: UserRecord, dimension: str, months: int = 0, min_admissions: int = 20, limit: int = 15) -> Dict[str, Any]:
    if dimension not in READMISSION_DIMENSIONS:
        raise ValueError(f"dimension must be one of {sorted(READMISSION_DIMENSIONS)}")
    expr = READMISSION_DIMENSIONS[dimension]
    window = ""
    if months and months > 0:
        window = f"WHERE CAST(admission_date AS DATE) > (SELECT max(CAST(admission_date AS DATE)) FROM gold_admissions) - INTERVAL {int(months)} MONTH"
    df = query_df_strict(f"""
        SELECT {expr} AS grp, COUNT(*) AS admissions, SUM(readmitted_30d) AS unplanned_readmissions,
               ROUND(AVG(readmitted_30d) * 100, 2) AS rate_pct
        FROM gold_admissions {window}
        GROUP BY 1 HAVING COUNT(*) >= ? ORDER BY rate_pct DESC, admissions DESC LIMIT ?
    """, [max(1, int(min_admissions)), max(1, min(int(limit), 50))])
    return {
        "dimension": dimension, "window": f"last {months} months of data" if months else "all data",
        "definition": "Unplanned 30-day readmission (planned same-reason repeat stays, transfers and in-hospital deaths excluded).",
        "groups_shown_have_at_least_admissions": int(min_admissions),
        "reliability_note": "rate_pct is an observed rate; ci95 is its 95% Wilson confidence range. Small groups have wide ranges, so overlapping ranges mean the ranking is uncertain.",
        "rows": [{"group": str(r.grp), "admissions": int(r.admissions), "unplanned_readmissions": int(r.unplanned_readmissions or 0),
                  "rate_pct": float(r.rate_pct or 0), "ci95_pct": _wilson(int(r.unplanned_readmissions or 0), int(r.admissions))} for r in df.itertuples()],
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


def get_admissions_trend(user: UserRecord, months: int = 12) -> Dict[str, Any]:
    from backend.app.services import executive

    rows = executive.get_admissions_trend(max(6, min(int(months), 120)))
    return {"unit": "monthly admissions (value) and unplanned readmissions (secondary)", "rows": _dump(rows)}


def get_revenue_by_department(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    return {"currency": "USD", "basis": "billed amount, all inpatient claims", "rows": _dump(executive.get_revenue_by_department())}


def get_capacity_plan(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import executive

    return _dump(executive.get_capacity_plan())


def get_readmission_economics(user: UserRecord) -> Dict[str, Any]:
    from backend.app.services import command

    return _dump(command.get_readmission_economics())


def list_hospitals_by_access_pressure(user: UserRecord, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import command

    return {"data_source": "SIMULATED operations data", "rows": _dump(command.list_hospitals()[: max(1, min(int(limit), 91))])}


def run_capacity_what_if(user: UserRecord, extra_visits_per_physician: float = 0, extra_physicians: int = 0, demand_change_pct: float = 0,
                         hospital_id: Optional[str] = None, period: str = "pre_covid_365") -> Dict[str, Any]:
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

def get_highest_risk_discharges(user: UserRecord, limit: int = 10) -> Dict[str, Any]:
    from backend.app.services import clinical

    rows = _strip_names(_dump(clinical.get_huddle(max(1, min(int(limit), 25)))))
    return {"basis": "recent discharges ranked by the readmission model's predicted probability", "rows": rows}


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

    line = pharmacy._stock_line(inventory_id)  # 404s on an unknown line
    a = actions.propose(
        kind="purchase_order", requested_by=user, agent=_ctx["agent"], session_id=_ctx.get("session_id"),
        payload={"inventory_id": inventory_id, "quantity": int(quantity)}, reason=reason,
        summary=f"Purchase order: {int(quantity)} units of {line['medication_name']} for {line.get('hospital_name') or 'site'}",
    )
    return {"status": "pending_approval", "action_id": a.action_id, "summary": a.summary,
            "note": "Nothing has been ordered. A pharmacist or administrator must approve this in the approval inbox."}


def propose_follow_up(user: UserRecord, patient_id: str, reason: str, due_in_days: int = 7, _ctx: Dict[str, Any] = None) -> Dict[str, Any]:
    from backend.app.agents import actions
    from backend.app.services import clinical

    clinical._patient_row(patient_id)  # 404s on an unknown patient
    a = actions.propose(
        kind="follow_up", requested_by=user, agent=(_ctx or {}).get("agent", ""), session_id=(_ctx or {}).get("session_id"),
        payload={"patient_id": patient_id, "due_in_days": max(1, min(int(due_in_days), 90))}, reason=reason,
        summary=f"Follow-up for {patient_id} within {max(1, min(int(due_in_days), 90))} days",
    )
    return {"status": "pending_approval", "action_id": a.action_id, "summary": a.summary,
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

    Tool("get_network_kpis", "Network-wide KPIs from Gold: admissions, patients, unplanned 30-day readmission rate, average length of stay, bed occupancy, billed revenue, collection rate, hospital count, data-through date.",
         {}, get_network_kpis, "insight", page="executive"),
    Tool("get_readmissions_by", "Unplanned 30-day readmission rates grouped by hospital, department, admission_type, admission_reason or age_band, highest first. Use for 'which hospital/department has the highest readmission rate'.",
         {"dimension": _s("Grouping", enum=sorted(READMISSION_DIMENSIONS)), "months": _i("Only the last N months of data; 0 = all data", minimum=0, maximum=120),
          "min_admissions": _i("Hide groups with fewer admissions than this (small groups have noisy rates)", minimum=1, maximum=10000),
          "limit": _i("Max rows", minimum=1, maximum=50)},
         get_readmissions_by, "insight", page="executive", required=["dimension"]),
    Tool("get_admissions_trend", "Monthly admissions and unplanned readmissions for the last N months of data.",
         {"months": _i("Months of history (6-120)", minimum=6, maximum=120)}, get_admissions_trend, "insight", page="executive"),
    Tool("get_revenue_by_department", "Billed revenue (USD) and admissions per department.", {}, get_revenue_by_department, "insight", page="executive"),
    Tool("get_capacity_plan", "Next-7-day capacity outlook: surge tier, occupancy, projected daily admissions, directives.", {}, get_capacity_plan, "insight", page="executive"),
    Tool("get_readmission_economics", "Facts for a post-discharge programme: discharges, readmissions, cost per stay, model flag/capture rates.",
         {}, get_readmission_economics, "insight", page="command"),
    Tool("list_hospitals_by_access_pressure", "Hospitals ranked by outpatient access pressure (share of demand served, wait days). SIMULATED operations data.",
         {"limit": _i("Max rows", minimum=1, maximum=91)}, list_hospitals_by_access_pressure, "insight", page="command"),
    Tool("run_capacity_what_if", "Replay a year of outpatient demand with changed staffing or demand and return waiting list, wait, lost patients, revenue and staffing cost vs baseline. SIMULATED operations data.",
         {"extra_visits_per_physician": _n("Extra visits per doctor per day (0-15)", minimum=0, maximum=15),
          "extra_physicians": _i("Extra physicians per hospital (0-50)", minimum=0, maximum=50),
          "demand_change_pct": _n("Demand change in percent (-50 to 100)", minimum=-50, maximum=100),
          "hospital_id": _s("One hospital id (from list_hospitals_by_access_pressure); omit for the whole network"),
          "period": _s("Replay window", enum=["pre_covid_365", "last_365", "last_90"])},
         run_capacity_what_if, "insight", page="command"),
    Tool("list_model_scores", "Every active ML model with its held-out score vs a baseline, data source, version and health.", {}, list_model_scores, "insight", page="command"),

    Tool("get_highest_risk_discharges", "Recent discharges ranked by predicted 30-day readmission probability, with drivers and whether a follow-up exists. Pseudonymous patient IDs only.",
         {"limit": _i("Max patients (1-25)", minimum=1, maximum=25)}, get_highest_risk_discharges, "care", page="doctor"),
    Tool("get_patient_summary", "Patient 360 for one patient ID (e.g. P_04436): age, risk tier, admissions, labs, prescriptions, comorbidities, care gaps, COVID risk. Every call is audited.",
         {"patient_id": _s("Patient ID like P_04436", pattern=r"^P_\d{1,6}$")}, get_patient_summary, "care", page="doctor", required=["patient_id"]),
    Tool("get_care_gap_summary", "Count of patients per care gap (overdue HbA1c, BP, eGFR, missing follow-up).", {}, get_care_gap_summary, "care", page="doctor"),
    Tool("list_care_gaps", "Patients with a care gap, optionally one gap type.",
         {"gap": _s("Gap code", enum=["diabetes_hba1c", "hypertension_bp", "ckd_egfr", "high_risk_no_follow_up"]), "limit": _i("Max rows", minimum=1, maximum=50)},
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
