"""
Clinical Workstation services (hcp role; admins oversee).

Morning huddle (recent discharges ranked by unplanned-readmission risk), care-gap radar,
patient search and Patient 360. Every patient-level view is audited.
"""

import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
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
    HuddlePatient,
    LabPoint,
    LabResultRow,
    LabSeries,
    MedicationRow,
    OutcomeRisk,
    Patient360,
    PatientRisk,
    PatientSummary,
)
from src.ml.model_registry import load_model
from src.ml.predict import (
    CLINICAL_DISCLAIMER,
    predict_patient_covid_outcomes,
    predict_patient_los,
    predict_patient_readmission,
    readmission_drivers,
)
from src.prescriptive.clinical_rules import get_clinical_prescription_plan
from src.security.audit import log_audit_event
from src.utils.database import query_df_strict

RECENT_DISCHARGE_DAYS = 30
FOLLOW_UP_WINDOW_DAYS = 14
GAP_LOOKBACK_DAYS = 365

# Care-gap rules: chronic condition (ICD-10 prefixes) without the guideline monitoring test in the lookback window
GAP_RULES = {
    "diabetes_hba1c": ("Diabetes without HbA1c", ["E11"], ["HbA1c"], "ADA: HbA1c at least every 6–12 months"),
    "hypertension_bp": ("Hypertension without BP check", ["I10"], ["Systolic Blood Pressure"], "Blood pressure reviewed at least yearly"),
    "ckd_egfr": ("CKD without kidney function test", ["N18", "E11.2"], ["eGFR", "Creatinine"], "KDIGO: eGFR / creatinine at least yearly"),
}
FOLLOW_UP_GAP = ("high_risk_no_follow_up", "High-risk discharge without follow-up", "TCP: follow-up visit within 7–14 days of discharge")

_score_lock = threading.Lock()
_score_cache: Dict[str, pd.DataFrame] = {}


def _data_end() -> pd.Timestamp:
    return pd.Timestamp(query_df_strict("SELECT max(test_date) AS d FROM gold_laboratory").iloc[0]["d"])


def _readmission_scores() -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Score every admission once per model version (≈10k rows); cached in-process."""
    artifact = load_model("readmission_risk_model")
    if not artifact:
        raise APIError(503, "model_unavailable", "The readmission model is not trained yet.")
    key = str(artifact.get("trained_at"))
    with _score_lock:
        if key not in _score_cache:
            feats = query_df_strict("SELECT * FROM gold_patient_risk_features")
            X = feats.reindex(columns=artifact["features"]).apply(pd.to_numeric, errors="coerce").fillna(0)
            feats["readmission_probability"] = artifact["model"].predict_proba(X)[:, 1]
            _score_cache.clear()
            _score_cache[key] = feats
        return _score_cache[key], artifact.get("risk_bands", {})


def _risk_level(p: float, bands: Dict[str, float]) -> str:
    return "HIGH" if p >= bands.get("high", 0.7) else "MODERATE" if p >= bands.get("moderate", 0.35) else "LOW"


def _huddle_frame() -> Tuple[pd.DataFrame, Dict[str, float]]:
    scores, bands = _readmission_scores()
    end = _data_end()
    adm = query_df_strict("""
        SELECT a.admission_id, a.patient_id, a.discharge_date, a.admission_reason, a.department_name, a.discharge_disposition,
               p.name, p.age AS current_age, p.gender, p.is_deceased
        FROM gold_admissions a JOIN gold_patient_360 p USING (patient_id)
    """)
    adm["_dis"] = pd.to_datetime(adm["discharge_date"], errors="coerce")
    recent = adm[(adm["_dis"] > end - pd.Timedelta(days=RECENT_DISCHARGE_DAYS)) & (adm["discharge_disposition"] != "Deceased")]
    recent = recent[pd.to_numeric(recent["is_deceased"], errors="coerce").fillna(0) == 0]
    # Latest discharge per patient only
    recent = recent.sort_values(["_dis", "admission_id"]).groupby("patient_id").tail(1)
    df = recent.merge(scores, on=["admission_id", "patient_id"], how="inner", suffixes=("", "_f"))

    visits = query_df_strict("""
        SELECT patient_id, CAST(appointment_date AS DATE) AS d FROM gold_appointments
        WHERE status = 'Completed' AND patient_id IN (SELECT patient_id FROM gold_admissions)
    """)
    visits["d"] = pd.to_datetime(visits["d"])
    fu = df[["patient_id", "_dis"]].merge(visits, on="patient_id", how="left")
    fu = fu[(fu["d"] >= fu["_dis"]) & (fu["d"] <= fu["_dis"] + pd.Timedelta(days=FOLLOW_UP_WINDOW_DAYS))]
    df["has_follow_up"] = df["patient_id"].isin(set(fu["patient_id"]))
    df["risk_level"] = [_risk_level(p, bands) for p in df["readmission_probability"]]
    return df.sort_values("readmission_probability", ascending=False), bands


def get_huddle(limit: int = 25) -> List[HuddlePatient]:
    df, _ = _huddle_frame()
    return [
        HuddlePatient(
            patient_id=r.patient_id, name=r.name, age=int(r.age), gender=r.gender, admission_id=r.admission_id,
            discharge_date=str(r.discharge_date), admission_reason=r.admission_reason if isinstance(r.admission_reason, str) else None,
            department_name=r.department_name if isinstance(r.department_name, str) else None,
            readmission_probability_pct=round(float(r.readmission_probability) * 100, 1), risk_level=r.risk_level,
            drivers=readmission_drivers(r._asdict())[:3], has_follow_up=bool(r.has_follow_up),
        )
        for r in df.head(limit).itertuples()
    ]


def _chronic_gap_sql(patient_filter: str = "") -> str:
    parts = []
    for gap, (label, prefixes, tests, _) in GAP_RULES.items():
        cond = " OR ".join(f"d.icd10_code LIKE '{p}%'" for p in prefixes)
        test_list = ", ".join(f"'{t}'" for t in tests)
        parts.append(f"""
            SELECT p.patient_id, p.name, p.age, '{gap}' AS gap, '{label}' AS label,
                   (SELECT max(test_date) FROM gold_laboratory l WHERE l.patient_id = p.patient_id AND l.test_name IN ({test_list})) AS last_done
            FROM gold_patient_360 p
            WHERE (p.is_deceased = 0 OR p.is_deceased = '0') {patient_filter}
              AND EXISTS (SELECT 1 FROM gold_clinical d WHERE d.patient_id = p.patient_id AND ({cond}))
              AND NOT EXISTS (SELECT 1 FROM gold_laboratory l WHERE l.patient_id = p.patient_id AND l.test_name IN ({test_list})
                              AND CAST(l.test_date AS DATE) > CAST(? AS DATE) - INTERVAL {GAP_LOOKBACK_DAYS} DAY)
        """)
    return " UNION ALL ".join(parts)


def _gap_detail(gap: str, last_done: Optional[str]) -> str:
    rule = GAP_RULES.get(gap)
    test = " / ".join(rule[2]) if rule else "test"
    return f"No {test} in the last 12 months" + (f" (last on {last_done})" if last_done else " (never recorded)")


def _follow_up_gaps(df: pd.DataFrame, bands: Dict[str, float]) -> pd.DataFrame:
    high = df[(df["risk_level"] == "HIGH") & (~df["has_follow_up"])]
    return pd.DataFrame({
        "patient_id": high["patient_id"], "name": high["name"], "age": high["age"],
        "gap": FOLLOW_UP_GAP[0], "label": FOLLOW_UP_GAP[1], "last_done": high["discharge_date"].astype(str),
    })


def _all_gaps(patient_id: Optional[str] = None) -> pd.DataFrame:
    end = _data_end()
    filt = "AND p.patient_id = ?" if patient_id else ""
    params: list = []
    for _ in GAP_RULES:
        if patient_id:
            params.append(patient_id)
        params.append(str(end.date()))
    chronic = query_df_strict(_chronic_gap_sql(filt), params)
    huddle, bands = _huddle_frame()
    fu = _follow_up_gaps(huddle, bands)
    if patient_id:
        fu = fu[fu["patient_id"] == patient_id]
    return pd.concat([chronic, fu], ignore_index=True)


def _gap_rows(df: pd.DataFrame) -> List[CareGap]:
    out = []
    for r in df.itertuples():
        last = None if r.last_done is None or r.last_done != r.last_done else str(r.last_done)
        detail = f"Discharged {last}; no outpatient visit within {FOLLOW_UP_WINDOW_DAYS} days" if r.gap == FOLLOW_UP_GAP[0] else _gap_detail(r.gap, last)
        out.append(CareGap(patient_id=r.patient_id, name=r.name, age=int(r.age), gap=r.gap, label=r.label, detail=detail, last_done=last))
    return out


def get_care_gap_summary() -> List[CareGapSummary]:
    df = _all_gaps()
    counts = df.groupby("gap")["patient_id"].nunique().to_dict()
    rules = [(g, label, guide) for g, (label, _, _, guide) in GAP_RULES.items()] + [FOLLOW_UP_GAP]
    return [CareGapSummary(gap=g, label=label, patients=int(counts.get(g, 0)), guideline=guide) for g, label, guide in rules]


def list_care_gaps(params: PageParams, gap: Optional[str] = None) -> Page[CareGap]:
    df = _all_gaps()
    if gap:
        if gap not in GAP_RULES and gap != FOLLOW_UP_GAP[0]:
            raise APIError(400, "unknown_gap", f"Unknown care gap '{gap}'.")
        df = df[df["gap"] == gap]
    order = {FOLLOW_UP_GAP[0]: 0, **{g: i + 1 for i, g in enumerate(GAP_RULES)}}
    df = df.assign(_o=df["gap"].map(order)).sort_values(["_o", "age"], ascending=[True, False])
    window = df.iloc[params.offset: params.offset + params.limit + 1]
    return build_page(_gap_rows(window), params)


def get_kpis() -> ClinicalKpis:
    r = query_df_strict("""
        SELECT COUNT(*) FILTER (WHERE is_deceased = 0 OR is_deceased = '0') AS living,
               COUNT(*) FILTER (WHERE (is_deceased = 0 OR is_deceased = '0') AND clinical_risk_tier = 'High') AS high
        FROM gold_patient_360
    """).iloc[0]
    huddle, _ = _huddle_frame()
    gaps = _all_gaps()
    return ClinicalKpis(
        living_patients=int(r["living"]),
        high_tier_patients=int(r["high"]),
        recent_discharges=int(len(huddle)),
        high_risk_recent_discharges=int((huddle["risk_level"] == "HIGH").sum()),
        open_care_gaps=int(len(gaps.drop_duplicates(["patient_id", "gap"]))),
        data_through=str(_data_end().date()),
    )


def search_patients(params: PageParams, search: Optional[str] = None, tier: Optional[str] = None) -> Page[PatientSummary]:
    where, args = ["1=1"], []
    if search:
        where.append("(patient_id ILIKE ? OR name ILIKE ?)")
        args += [f"%{search}%", f"%{search}%"]
    if tier:
        where.append("clinical_risk_tier = ?")
        args.append(tier)
    df = query_df_strict(
        f"""SELECT patient_id, name, age, gender, clinical_risk_tier, total_admissions, is_deceased FROM gold_patient_360
            WHERE {' AND '.join(where)}
            ORDER BY CASE WHEN is_deceased = 0 OR is_deceased = '0' THEN 0 ELSE 1 END,
                     CASE clinical_risk_tier WHEN 'High' THEN 0 WHEN 'Moderate' THEN 1 ELSE 2 END, total_admissions DESC, patient_id
            LIMIT ? OFFSET ?""",
        args + [params.limit + 1, params.offset],
    )
    rows = [
        PatientSummary(patient_id=r.patient_id, name=r.name, age=int(r.age), gender=r.gender, clinical_risk_tier=r.clinical_risk_tier,
                       total_admissions=int(r.total_admissions), is_deceased=str(r.is_deceased) in ("1", "True"))
        for r in df.itertuples()
    ]
    return build_page(rows, params)


def _patient_row(patient_id: str) -> pd.Series:
    df = query_df_strict("SELECT * FROM gold_patient_360 WHERE patient_id = ?", [patient_id])
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

    def num(col, default=0):
        v = pd.to_numeric(p.get(col), errors="coerce")
        return default if v is None or v != v else v

    flags = {f: bool(int(num(f))) for f in ["has_hypertension", "has_diabetes", "has_copd", "has_heart_failure", "has_ckd", "has_cancer", "has_obesity"]}
    return Patient360(
        patient_id=patient_id, name=str(p["name"]), age=int(num("age")), gender=str(p["gender"]),
        blood_group=p.get("blood_group"), insurance_provider=p.get("insurance_provider"), city=p.get("city"),
        is_deceased=bool(int(num("is_deceased"))), death_date=p.get("death_date") if isinstance(p.get("death_date"), str) else None,
        clinical_risk_tier=str(p["clinical_risk_tier"]), total_admissions=int(num("total_admissions")),
        average_los_days=round(float(num("avg_los")), 1), unplanned_readmissions=int(num("prior_readmissions")),
        total_lab_tests=int(num("total_lab_tests")), abnormal_lab_count=int(num("abnormal_lab_count")),
        critical_lab_count=int(num("critical_lab_count")), active_prescriptions=int(num("active_prescriptions_count")),
        lifetime_billing=round(float(num("lifetime_billing")), 2),
        comorbidities=[str(d) for d in dx["diagnosis_description"]], flags=flags,
        care_gaps=_gap_rows(_all_gaps(patient_id)),
    )


def get_patient_risk(patient_id: str, user: UserRecord) -> PatientRisk:
    p = _patient_row(patient_id)
    _audit_view(user, patient_id, "risk_predictions")
    covid = predict_patient_covid_outcomes(patient_id)
    readm = predict_patient_readmission(patient_id)
    los = predict_patient_los(patient_id)
    profile = {k: pd.to_numeric(p.get(k), errors="coerce") for k in ["has_heart_failure", "has_diabetes", "critical_lab_count"]}
    plan = get_clinical_prescription_plan(readm if readm.get("status") == "SUCCESS" else {"risk_level": "LOW", "probability": 0.0}, profile)
    ok = readm.get("status") == "SUCCESS"
    return PatientRisk(
        covid_scored_as_of=covid.get("scored_as_of"),
        covid_outcomes=[
            OutcomeRisk(outcome=k, label=v["label"], probability_pct=v["probability"], risk_level=v["risk_level"],
                        cohort_rate_pct=v["cohort_rate_pct"], observed=v["observed"])
            for k, v in covid.get("outcomes", {}).items()
        ],
        covid_drivers=covid.get("risk_drivers", []),
        readmission_available=ok,
        readmission_probability_pct=readm.get("probability") if ok else None,
        readmission_risk_level=readm.get("risk_level") if ok else None,
        readmission_base_rate_pct=readm.get("cohort_base_rate_pct") if ok else None,
        readmission_drivers=readm.get("contributing_factors", []) if ok else [],
        readmission_admission_date=readm.get("admission_date") if ok else None,
        los_predicted_days=los.get("predicted_los_days") if los.get("status") == "SUCCESS" else None,
        los_observed_days=float(los["observed_los_days"]) if los.get("status") == "SUCCESS" and los.get("observed_los_days") is not None else None,
        los_interval=los.get("confidence_interval") if los.get("status") == "SUCCESS" else None,
        care_plan=CarePlan(
            pathway=plan["care_tier"], primary_recommendation=plan["primary_recommendation"],
            checklist=plan["actionable_checklist"], rationale=plan["clinical_rationale"], disclaimer=plan["disclaimer"],
        ),
        disclaimer=CLINICAL_DISCLAIMER,
    )


def _f(v) -> Optional[float]:
    v = pd.to_numeric(v, errors="coerce")
    return None if v is None or v != v else round(float(v), 2)


def _s(v) -> Optional[str]:
    return v if isinstance(v, str) and v not in ("", "standard") else None


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
               department_name, discharge_disposition, is_icu, readmitted_30d
        FROM gold_admissions WHERE patient_id = ? ORDER BY admission_date DESC
    """, [patient_id])
    dx = query_df_strict("SELECT admission_id, diagnosis_description FROM gold_clinical WHERE patient_id = ? AND admission_id IS NOT NULL", [patient_id])
    by_adm = dx.groupby("admission_id")["diagnosis_description"].apply(lambda s: sorted(set(map(str, s)))).to_dict() if not dx.empty else {}
    return [
        EncounterRow(
            admission_id=r.admission_id, admission_date=str(r.admission_date), discharge_date=str(r.discharge_date),
            length_of_stay_days=_f(r.length_of_stay_days), admission_type=str(r.admission_type), admission_reason=_s(r.admission_reason),
            department_name=_s(r.department_name), discharge_disposition=str(r.discharge_disposition),
            is_icu=bool(int(np.nan_to_num(pd.to_numeric(r.is_icu, errors="coerce")))), readmitted_30d=bool(int(r.readmitted_30d or 0)),
            diagnoses=by_adm.get(r.admission_id, [])[:8],
        )
        for r in adm.itertuples()
    ]
