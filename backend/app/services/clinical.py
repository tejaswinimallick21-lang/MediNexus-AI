"""
Oncology Workstation services (hcp role; admins oversee).

Tumour-board worklist (living cancer patients ranked by 12-month mortality risk), oncology care-gap
radar, patient search and Patient 360 with the treatment timeline. Every patient-level view is audited.
"""

import threading
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.core.users import UserRecord
from backend.app.schemas.clinical import (
    CareGap,
    CareGapSummary,
    CarePlan,
    ClinicalKpis,
    EncounterRow,
    LabPoint,
    LabResultRow,
    LabSeries,
    MedicationRow,
    Patient360,
    PatientRisk,
    PatientSummary,
    SurvivalBenchmark,
    TreatmentEvent,
    WorklistPatient,
)
from src.ml.model_registry import load_model
from src.ml.predict import CLINICAL_DISCLAIMER, predict_patient_outcome_risk
from src.prescriptive.clinical_rules import get_oncology_care_plan
from src.security.audit import log_audit_event
from src.utils.database import query_df_strict

INFUSION_TYPES = ("Chemotherapy", "Immunotherapy", "Targeted therapy")
TIME_TO_TREATMENT_DAYS = 30     # target: first treatment within 30 days of diagnosis
CBC_BEFORE_CYCLE_DAYS = 7       # a blood count within 7 days before each systemic cycle
SURVIVORSHIP_VISIT_DAYS = 180   # follow-up at least every 6 months after treatment
RECENT_INFUSION_DAYS = 30

# gap: (label, guideline)
GAP_RULES = {
    "treatment_delay": ("Diagnosed, treatment not started", "First treatment within 30 days of diagnosis (time-to-treatment standard)"),
    "chemo_no_cbc": ("Systemic cycle without a recent blood count", "Full blood count within 7 days before each chemotherapy / immunotherapy cycle"),
    "rising_marker": ("Rising tumour marker after treatment", "Investigate a rising, above-range marker for recurrence"),
    "follow_up_overdue": ("Survivorship follow-up overdue", "Follow-up every 3-6 months after treatment"),
    "goals_of_care": ("High risk, no palliative review", "Early palliative care for patients with a high risk of dying within a year"),
}

_score_lock = threading.Lock()
_score_cache: Dict[str, pd.DataFrame] = {}


def _data_end() -> pd.Timestamp:
    return pd.Timestamp(query_df_strict("SELECT max(test_date) AS d FROM gold_laboratory").iloc[0]["d"])


def _risk_level(p: float, bands: Dict[str, float]) -> str:
    return "HIGH" if p >= bands.get("high", 0.7) else "MODERATE" if p >= bands.get("moderate", 0.35) else "LOW"


def _mortality_scores() -> pd.DataFrame:
    """12-month mortality risk for every living cancer patient (served method), cached per model version."""
    artifact = load_model("outcome_risk_model")
    if not artifact or "died_12m" not in artifact.get("models", {}):
        raise APIError(503, "model_unavailable", "The 12-month mortality model is not trained yet.")
    key = str(artifact.get("trained_at"))
    with _score_lock:
        if key not in _score_cache:
            spec = artifact["models"]["died_12m"]
            rows = query_df_strict("SELECT * FROM gold_outcome_risk WHERE snapshot = 'score'")
            if spec.get("serving_method") == "stage_type_baseline":
                X = rows.reindex(columns=spec["baseline_features"]).apply(pd.to_numeric, errors="coerce").fillna(spec["baseline_fill"])
                proba = spec["baseline_model"].predict_proba(X)[:, 1]
            else:
                X = rows.reindex(columns=artifact["features"]).apply(pd.to_numeric, errors="coerce")
                proba = spec["model"].predict_proba(X)[:, 1]
            rows["mortality_risk"] = proba
            rows["risk_level"] = [_risk_level(p, spec["risk_bands"]) for p in proba]
            _score_cache.clear()
            _score_cache[key] = rows
        return _score_cache[key]


def _oncology() -> pd.DataFrame:
    return query_df_strict("SELECT * FROM gold_oncology_patients")


def _scored_living() -> pd.DataFrame:
    """Living cancer patients joined to their mortality risk."""
    onc = _oncology()
    living = onc[pd.to_numeric(onc["is_deceased"], errors="coerce").fillna(0) == 0]
    scores = _mortality_scores()[["patient_id", "mortality_risk", "risk_level", "age_at_index",
                                  "marker_elevated", "has_heart_failure", "has_copd", "has_ckd", "has_coronary_disease", "has_diabetes"]]
    return living.merge(scores, on="patient_id", how="inner")


def _drivers(r) -> List[str]:
    out = []
    stage = int(r.stage_num or 0) if r.stage_num == r.stage_num else 0
    if stage >= 3:
        out.append(f"Stage {'IV' if stage == 4 else 'III'}")
    if r.cancer_type in ("Pancreas", "Lung"):
        out.append(f"{r.cancer_type}: low survival at every stage")
    if (r.age_at_index or 0) >= 75:
        out.append(f"Age {int(r.age_at_index)}")
    if r.marker_elevated == 1:
        out.append("Tumour marker above range")
    for flag, text in [("has_heart_failure", "Heart failure"), ("has_copd", "COPD"), ("has_ckd", "Chronic kidney disease")]:
        if getattr(r, flag, 0) == 1:
            out.append(text)
    return out[:3] or ["Early stage, no major risk factors"]


def _i(v) -> Optional[int]:
    v = pd.to_numeric(v, errors="coerce")
    return None if v is None or v != v else int(v)


def _f(v) -> Optional[float]:
    v = pd.to_numeric(v, errors="coerce")
    return None if v is None or v != v else round(float(v), 2)


def _s(v) -> Optional[str]:
    return v if isinstance(v, str) and v not in ("", "standard") else None


def get_worklist(limit: int = 25) -> List[WorklistPatient]:
    df = _scored_living().sort_values(["mortality_risk", "age", "patient_id"], ascending=[False, False, True])
    end = _data_end()
    out = []
    for r in df.head(limit).itertuples():
        dx = pd.to_datetime(r.diagnosis_date, errors="coerce")
        out.append(WorklistPatient(
            patient_id=r.patient_id, name=r.name, age=int(r.age), gender=r.gender, cancer_type=r.cancer_type,
            cancer_stage=_s(r.cancer_stage), treatment_status=r.treatment_status, systemic_regimen=_s(r.systemic_regimen),
            days_since_diagnosis=None if pd.isna(dx) else int((end - dx).days), last_treatment_date=_s(r.last_treatment_date),
            mortality_risk_pct=round(float(r.mortality_risk) * 100, 1), risk_level=r.risk_level, drivers=_drivers(r),
            tumor_marker=_s(r.tumor_marker), marker_value=_f(r.marker_value), marker_trend=_s(r.marker_trend),
        ))
    return out


def _all_gaps(patient_id: Optional[str] = None) -> pd.DataFrame:
    """Open oncology care gaps: one row per (patient, gap)."""
    end = _data_end()
    df = _scored_living()
    if patient_id:
        df = df[df["patient_id"] == patient_id]
    days_since_dx = (end - pd.to_datetime(df["diagnosis_date"], errors="coerce")).dt.days
    rows = []

    def add(mask, gap, last_col, detail_fn):
        for r in df[mask].itertuples():
            rows.append({"patient_id": r.patient_id, "name": r.name, "age": int(r.age), "gap": gap, "label": GAP_RULES[gap][0],
                         "last_done": getattr(r, last_col) if last_col else None, "detail": detail_fn(r)})

    add((df["treatment_status"] == "Awaiting treatment") & (days_since_dx > TIME_TO_TREATMENT_DAYS), "treatment_delay", "diagnosis_date",
        lambda r: f"{r.cancer_type} stage {r.cancer_stage or '?'} diagnosed {r.diagnosis_date}; no treatment recorded yet")
    add(df["treatment_status"].isin(["Surveillance", "Watchful waiting"]) & (df["marker_trend"] == "Rising")
        & df["marker_flag"].isin(["High", "Critical"]), "rising_marker", "marker_date",
        lambda r: f"{r.tumor_marker} {r.marker_value} and rising on the last two results")
    last_visit = pd.to_datetime(df["last_visit_date"], errors="coerce")
    add((df["treatment_status"] == "Surveillance") & (last_visit < end - pd.Timedelta(days=SURVIVORSHIP_VISIT_DAYS)),
        "follow_up_overdue", "last_visit_date", lambda r: f"No visit since {r.last_visit_date}")
    add(df["risk_level"] == "HIGH", "goals_of_care", None,
        lambda r: f"12-month mortality risk {round(float(r.mortality_risk) * 100)}%; no hospice or palliative visit recorded")

    # Systemic cycle in the last 30 days without a white-cell count in the 7 days before it
    infusion = ", ".join(f"'{t}'" for t in INFUSION_TYPES)
    pfilter = "AND patient_id = ?" if patient_id else ""
    cbc = query_df_strict(f"""
        WITH last_cycle AS (
            SELECT patient_id, max(CAST(event_date AS DATE)) AS d FROM gold_treatment_events
            WHERE event_type IN ({infusion}) AND CAST(event_date AS DATE) > CAST(? AS DATE) - INTERVAL {RECENT_INFUSION_DAYS} DAY {pfilter}
            GROUP BY 1)
        SELECT c.patient_id, c.d AS cycle_date,
               (SELECT max(CAST(test_date AS DATE)) FROM gold_laboratory l WHERE l.patient_id = c.patient_id
                AND l.test_name = 'White Blood Cell Count' AND CAST(l.test_date AS DATE) <= c.d) AS last_cbc
        FROM last_cycle c
    """, [str(end.date())] + ([patient_id] if patient_id else []))
    if not cbc.empty:
        cbc["cycle_date"] = pd.to_datetime(cbc["cycle_date"])
        cbc["last_cbc"] = pd.to_datetime(cbc["last_cbc"])
        missing = cbc[cbc["last_cbc"].isna() | (cbc["last_cbc"] < cbc["cycle_date"] - pd.Timedelta(days=CBC_BEFORE_CYCLE_DAYS))]
        info = df.set_index("patient_id")
        for r in missing.itertuples():
            if r.patient_id in info.index:
                p = info.loc[r.patient_id]
                last = None if pd.isna(r.last_cbc) else r.last_cbc.strftime("%Y-%m-%d")
                rows.append({"patient_id": r.patient_id, "name": p["name"], "age": int(p["age"]), "gap": "chemo_no_cbc",
                             "label": GAP_RULES["chemo_no_cbc"][0], "last_done": last,
                             "detail": f"Cycle on {r.cycle_date:%Y-%m-%d}; last blood count {last or 'never recorded'}"})
    return pd.DataFrame(rows, columns=["patient_id", "name", "age", "gap", "label", "last_done", "detail"])


def _gap_rows(df: pd.DataFrame) -> List[CareGap]:
    return [CareGap(patient_id=r.patient_id, name=r.name, age=int(r.age), gap=r.gap, label=r.label, detail=r.detail,
                    last_done=_s(r.last_done)) for r in df.itertuples()]


def get_care_gap_summary() -> List[CareGapSummary]:
    df = _all_gaps()
    counts = df.groupby("gap")["patient_id"].nunique().to_dict()
    return [CareGapSummary(gap=g, label=label, patients=int(counts.get(g, 0)), guideline=guide) for g, (label, guide) in GAP_RULES.items()]


def list_care_gaps(params: PageParams, gap: Optional[str] = None) -> Page[CareGap]:
    df = _all_gaps()
    if gap:
        if gap not in GAP_RULES:
            raise APIError(400, "unknown_gap", f"Unknown care gap '{gap}'.")
        df = df[df["gap"] == gap]
    order = {g: i for i, g in enumerate(GAP_RULES)}
    df = df.assign(_o=df["gap"].map(order)).sort_values(["_o", "age", "patient_id"], ascending=[True, False, True])
    window = df.iloc[params.offset: params.offset + params.limit + 1]
    return build_page(_gap_rows(window), params)


def get_kpis() -> ClinicalKpis:
    df = _scored_living()
    gaps = _all_gaps()
    return ClinicalKpis(
        active_patients=int(len(df)),
        in_treatment=int((df["treatment_status"] == "In treatment").sum()),
        awaiting_treatment=int((df["treatment_status"] == "Awaiting treatment").sum()),
        high_mortality_risk=int((df["risk_level"] == "HIGH").sum()),
        open_care_gaps=int(len(gaps.drop_duplicates(["patient_id", "gap"]))),
        data_through=str(_data_end().date()),
    )


def search_patients(params: PageParams, search: Optional[str] = None, tier: Optional[str] = None,
                    cancer_type: Optional[str] = None, stage: Optional[str] = None) -> Page[PatientSummary]:
    where, args = ["1=1"], []
    if search:
        where.append("(p.patient_id ILIKE ? OR p.name ILIKE ?)")
        args += [f"%{search}%", f"%{search}%"]
    if tier:
        where.append("p.clinical_risk_tier = ?")
        args.append(tier)
    if cancer_type:
        where.append("p.cancer_type = ?")
        args.append(cancer_type)
    if stage:
        where.append("p.cancer_stage = ?")
        args.append(stage)
    df = query_df_strict(
        f"""SELECT p.patient_id, p.name, p.age, p.gender, p.cancer_type, p.cancer_stage, o.treatment_status, p.clinical_risk_tier, p.is_deceased
            FROM gold_patient_360 p LEFT JOIN gold_oncology_patients o USING (patient_id)
            WHERE {' AND '.join(where)}
            ORDER BY CASE WHEN p.is_deceased = 0 OR p.is_deceased = '0' THEN 0 ELSE 1 END,
                     CASE p.clinical_risk_tier WHEN 'High' THEN 0 WHEN 'Moderate' THEN 1 ELSE 2 END,
                     CASE p.cancer_stage WHEN 'IV' THEN 0 WHEN 'III' THEN 1 WHEN 'II' THEN 2 WHEN 'I' THEN 3 ELSE 4 END, p.patient_id
            LIMIT ? OFFSET ?""",
        args + [params.limit + 1, params.offset],
    )
    rows = [
        PatientSummary(patient_id=r.patient_id, name=r.name, age=int(r.age), gender=r.gender, cancer_type=_s(r.cancer_type),
                       cancer_stage=_s(r.cancer_stage), treatment_status=_s(r.treatment_status), clinical_risk_tier=r.clinical_risk_tier,
                       is_deceased=str(r.is_deceased) in ("1", "True"))
        for r in df.itertuples()
    ]
    return build_page(rows, params)


def _patient_row(patient_id: str) -> pd.Series:
    df = query_df_strict("""
        SELECT p.*, o.diagnosis_date, o.age_at_diagnosis, o.treatment_status, o.systemic_regimen, o.surgery_procedure, o.surgery_date,
               o.first_treatment_date, o.days_to_treatment, o.chemo_cycles, o.immunotherapy_cycles, o.targeted_therapy_cycles,
               o.radiation_sessions, o.tumor_marker, o.marker_value, o.marker_flag, o.marker_trend
        FROM gold_patient_360 p LEFT JOIN gold_oncology_patients o USING (patient_id) WHERE p.patient_id = ?
    """, [patient_id])
    if df.empty:
        raise APIError(404, "patient_not_found", f"No patient {patient_id}.")
    return df.iloc[0]


def _audit_view(user: UserRecord, patient_id: str, view: str) -> None:
    log_audit_event(username=user.email, role=user.role, action="PATIENT_VIEW", resource=patient_id, status="SUCCESS", details=view)


def get_patient_360(patient_id: str, user: UserRecord) -> Patient360:
    p = _patient_row(patient_id)
    _audit_view(user, patient_id, "patient_360")
    dx = query_df_strict("""
        SELECT diagnosis_description, max(diagnosis_date) AS last FROM gold_clinical
        WHERE patient_id = ? AND severity IN ('Moderate', 'Severe') GROUP BY 1 ORDER BY last DESC LIMIT 12
    """, [patient_id])
    flags = {f: bool(_i(p.get(f)) or 0) for f in ["has_hypertension", "has_diabetes", "has_copd", "has_heart_failure", "has_ckd", "has_obesity"]}
    deceased = bool(_i(p.get("is_deceased")) or 0)
    return Patient360(
        patient_id=patient_id, name=str(p["name"]), age=int(_i(p.get("age")) or 0), gender=str(p["gender"]),
        blood_group=_s(p.get("blood_group")), insurance_provider=_s(p.get("insurance_provider")), city=_s(p.get("city")),
        is_deceased=deceased, death_date=_s(p.get("death_date")), clinical_risk_tier=str(p["clinical_risk_tier"]),
        cancer_type=_s(p.get("cancer_type")), cancer_stage=_s(p.get("cancer_stage")), diagnosis_date=_s(p.get("diagnosis_date")),
        age_at_diagnosis=_i(p.get("age_at_diagnosis")), treatment_status=_s(p.get("treatment_status")),
        systemic_regimen=_s(p.get("systemic_regimen")), surgery_procedure=_s(p.get("surgery_procedure")), surgery_date=_s(p.get("surgery_date")),
        first_treatment_date=_s(p.get("first_treatment_date")), days_to_treatment=_i(p.get("days_to_treatment")),
        chemo_cycles=_i(p.get("chemo_cycles")) or 0, immunotherapy_cycles=_i(p.get("immunotherapy_cycles")) or 0,
        targeted_therapy_cycles=_i(p.get("targeted_therapy_cycles")) or 0, radiation_sessions=_i(p.get("radiation_sessions")) or 0,
        tumor_marker=_s(p.get("tumor_marker")), marker_value=_f(p.get("marker_value")), marker_flag=_s(p.get("marker_flag")),
        marker_trend=_s(p.get("marker_trend")),
        total_lab_tests=_i(p.get("total_lab_tests")) or 0, abnormal_lab_count=_i(p.get("abnormal_lab_count")) or 0,
        critical_lab_count=_i(p.get("critical_lab_count")) or 0, active_prescriptions=_i(p.get("active_prescriptions_count")) or 0,
        lifetime_billing=_f(p.get("lifetime_billing")) or 0.0,
        comorbidities=[str(d) for d in dx["diagnosis_description"]], flags=flags,
        care_gaps=[] if deceased else _gap_rows(_all_gaps(patient_id)),
    )


def _benchmark(cancer_type: Optional[str], stage: Optional[str]) -> Optional[SurvivalBenchmark]:
    if not cancer_type or not stage:
        return None
    label = f"{cancer_type} | Stage {stage}"
    df = query_df_strict("SELECT month, survival_pct, patients FROM gold_survival WHERE group_type = 'type_stage' AND group_label = ? AND month IN (12, 60)", [label])
    if df.empty:
        return None
    at = df.set_index("month")["survival_pct"]
    return SurvivalBenchmark(group=f"{cancer_type}, stage {stage}", patients=int(df["patients"].iloc[0]),
                             one_year_pct=_f(at.get(12)), five_year_pct=_f(at.get(60)))


def get_patient_risk(patient_id: str, user: UserRecord) -> PatientRisk:
    p = _patient_row(patient_id)
    _audit_view(user, patient_id, "risk_predictions")
    risk = predict_patient_outcome_risk(patient_id)
    ok = risk.get("status") == "SUCCESS" and "died_12m" in risk.get("outcomes", {})
    m = risk["outcomes"]["died_12m"] if ok else {}
    status = "Deceased" if _i(p.get("is_deceased")) else (_s(p.get("treatment_status")) or "Surveillance")
    plan = get_oncology_care_plan(m.get("risk_level", "LOW"), status, _s(p.get("cancer_stage")))
    return PatientRisk(
        available=ok, scored_as_of=risk.get("scored_as_of") if ok else None,
        mortality_12m_pct=m.get("probability"), risk_level=m.get("risk_level"), cohort_rate_pct=m.get("cohort_rate_pct"),
        method=m.get("method"), drivers=risk.get("risk_drivers", []) if ok else [],
        survival_benchmark=_benchmark(_s(p.get("cancer_type")), _s(p.get("cancer_stage"))),
        care_plan=CarePlan(pathway=plan["care_tier"], primary_recommendation=plan["primary_recommendation"],
                           checklist=plan["actionable_checklist"], rationale=plan["clinical_rationale"], disclaimer=plan["disclaimer"]),
        disclaimer=CLINICAL_DISCLAIMER,
    )


def get_treatments(patient_id: str) -> List[TreatmentEvent]:
    _patient_row(patient_id)
    df = query_df_strict("""
        SELECT event_date, event_type, detail, cycle, hospital_name FROM gold_treatment_events
        WHERE patient_id = ? ORDER BY event_date DESC, event_type
    """, [patient_id])
    return [TreatmentEvent(event_date=str(r.event_date), event_type=r.event_type, detail=_s(r.detail), cycle=_i(r.cycle),
                           hospital_name=_s(r.hospital_name)) for r in df.itertuples()]


def get_lab_tests(patient_id: str) -> List[str]:
    _patient_row(patient_id)
    df = query_df_strict("SELECT test_name, COUNT(*) n FROM gold_laboratory WHERE patient_id = ? GROUP BY 1 ORDER BY n DESC", [patient_id])
    return [str(t) for t in df["test_name"]]


def get_lab_series(patient_id: str, test_name: str) -> LabSeries:
    df = query_df_strict("""
        SELECT test_date, test_value, unit, reference_range, abnormal_flag FROM gold_laboratory
        WHERE patient_id = ? AND test_name = ? ORDER BY test_date
    """, [patient_id, test_name])
    if df.empty:
        raise APIError(404, "lab_series_not_found", f"No {test_name} results for {patient_id}.")
    return LabSeries(
        test_name=test_name, unit=_s(df["unit"].dropna().iloc[0]) if df["unit"].notna().any() else None,
        reference_range=_s(df["reference_range"].iloc[-1]),
        points=[LabPoint(test_date=str(r.test_date), test_value=_f(r.test_value), abnormal_flag=str(r.abnormal_flag)) for r in df.itertuples()],
    )


def get_recent_labs(patient_id: str, params: PageParams) -> Page[LabResultRow]:
    df = query_df_strict("""
        SELECT test_date, test_name, test_value, unit, reference_range, abnormal_flag FROM gold_laboratory
        WHERE patient_id = ? ORDER BY test_date DESC, test_name LIMIT ? OFFSET ?
    """, [patient_id, params.limit + 1, params.offset])
    rows = [LabResultRow(test_date=str(r.test_date), test_name=r.test_name, test_value=_f(r.test_value), unit=_s(r.unit),
                         reference_range=_s(r.reference_range), abnormal_flag=str(r.abnormal_flag)) for r in df.itertuples()]
    return build_page(rows, params)


def get_medications(patient_id: str, params: PageParams) -> Page[MedicationRow]:
    _patient_row(patient_id)
    df = query_df_strict("""
        SELECT prescription_date, end_date, medication_name, medication_category, dosage, status, indication FROM gold_prescriptions
        WHERE patient_id = ? ORDER BY CASE status WHEN 'Active' THEN 0 ELSE 1 END, prescription_date DESC LIMIT ? OFFSET ?
    """, [patient_id, params.limit + 1, params.offset])
    rows = [MedicationRow(prescription_date=str(r.prescription_date), end_date=_s(r.end_date), medication_name=_s(r.medication_name),
                          category=_s(r.medication_category), dosage=_s(r.dosage), status=str(r.status), indication=_s(r.indication))
            for r in df.itertuples()]
    return build_page(rows, params)


def get_encounters(patient_id: str) -> List[EncounterRow]:
    _patient_row(patient_id)
    adm = query_df_strict("""
        SELECT admission_id, admission_date, discharge_date, length_of_stay_days, admission_type, admission_reason,
               department_name, discharge_disposition, surgery_procedure
        FROM gold_admissions WHERE patient_id = ? ORDER BY admission_date DESC
    """, [patient_id])
    dx = query_df_strict("SELECT admission_id, diagnosis_description FROM gold_clinical WHERE patient_id = ? AND admission_id IS NOT NULL", [patient_id])
    by_adm = dx.groupby("admission_id")["diagnosis_description"].apply(lambda s: sorted(set(map(str, s)))).to_dict() if not dx.empty else {}
    return [
        EncounterRow(
            admission_id=r.admission_id, admission_date=str(r.admission_date), discharge_date=str(r.discharge_date),
            length_of_stay_days=_f(r.length_of_stay_days), admission_type=str(r.admission_type), admission_reason=_s(r.admission_reason),
            department_name=_s(r.department_name), discharge_disposition=str(r.discharge_disposition),
            surgery_procedure=_s(r.surgery_procedure), diagnoses=by_adm.get(r.admission_id, [])[:8],
        )
        for r in adm.itertuples()
    ]
