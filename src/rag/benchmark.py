"""
Retrieval benchmark for the knowledge library: compares BM25, dense and hybrid search.

Four suites:
  keyword     the question reuses the document's own words (easy for keyword search)
  exact       policy codes and specific figures (keyword search should win)
  paraphrase  the same need in everyday words, avoiding the document's key terms (needs meaning)
  out_scope   questions the library cannot answer; the correct result is "nothing found"

Metrics: hit@1, hit@3, MRR@3 on in-scope questions; abstention accuracy on out-of-scope ones;
false-refusal rate (in-scope questions that returned nothing).
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List

from src.rag.hybrid import CACHE_DIR, HybridIndex, get_index

CASES: List[Dict[str, str]] = [
    # (expected document stem, suite, question)
    {"doc": "medication_storage_policy", "suite": "keyword", "q": "What temperature range is required for refrigerated medications?"},
    {"doc": "medication_storage_policy", "suite": "paraphrase", "q": "How cold does insulin need to be kept in the fridge?"},
    {"doc": "inventory_policy", "suite": "keyword", "q": "What is the reorder policy for pharmacy inventory stock?"},
    {"doc": "inventory_policy", "suite": "paraphrase", "q": "When should we buy more of a medicine before we run out?"},
    {"doc": "laboratory_safety_policy", "suite": "keyword", "q": "What are the BSL-2 biosafety precautions and analyzer maintenance standards?"},
    {"doc": "laboratory_safety_policy", "suite": "paraphrase", "q": "Someone spilled a little blood on the bench - how do we clean it up?"},
    {"doc": "sample_handling_policy", "suite": "keyword", "q": "What is the critical value notification and escalation protocol for lab results?"},
    {"doc": "sample_handling_policy", "suite": "paraphrase", "q": "A blood test result is dangerously abnormal - who do I have to call and how fast?"},
    {"doc": "discharge_policy", "suite": "keyword", "q": "What is the discharge planning policy for high readmission risk patients?"},
    {"doc": "discharge_policy", "suite": "paraphrase", "q": "What must happen before a patient who might come back soon is sent home?"},
    {"doc": "readmission_followup_guideline", "suite": "keyword", "q": "What does the readmission follow-up guideline say about heart failure?"},
    {"doc": "readmission_followup_guideline", "suite": "paraphrase", "q": "How soon after going home should a cardiac patient with fluid problems be seen again?"},
    {"doc": "appointment_policy", "suite": "keyword", "q": "What is the appointment no-show and cancellation policy?"},
    {"doc": "appointment_policy", "suite": "paraphrase", "q": "What happens if someone keeps missing their clinic visits?"},
    {"doc": "patient_privacy_policy", "suite": "keyword", "q": "What does the patient privacy policy require for health records?"},
    {"doc": "patient_privacy_policy", "suite": "paraphrase", "q": "Who is allowed to look at a person's medical chart?"},
    {"doc": "hand_hygiene_policy", "suite": "keyword", "q": "What are the five moments of hand hygiene?"},
    {"doc": "hand_hygiene_policy", "suite": "paraphrase", "q": "Is hand gel enough after looking after someone with C. diff diarrhoea?"},
    {"doc": "sepsis_screening_protocol", "suite": "keyword", "q": "What is the sepsis screening protocol and first-hour bundle?"},
    {"doc": "sepsis_screening_protocol", "suite": "paraphrase", "q": "A patient with an infection has a fast breathing rate and low blood pressure - what do we do in the first hour?"},
    {"doc": "isolation_precautions_policy", "suite": "keyword", "q": "Which isolation precautions apply to tuberculosis and measles?"},
    {"doc": "isolation_precautions_policy", "suite": "paraphrase", "q": "What mask and room does a patient with an airborne disease need?"},
    {"doc": "fall_prevention_guideline", "suite": "keyword", "q": "What is the inpatient fall prevention risk assessment?"},
    {"doc": "fall_prevention_guideline", "suite": "paraphrase", "q": "An elderly patient slipped out of bed and hit their head - what now?"},
    {"doc": "medication_reconciliation_guideline", "suite": "keyword", "q": "How is medication reconciliation done at admission and discharge?"},
    {"doc": "medication_reconciliation_guideline", "suite": "paraphrase", "q": "How do we make sure the pills a patient takes at home match what we prescribe?"},
    {"doc": "inpatient_glucose_management", "suite": "keyword", "q": "What are the inpatient glucose targets and hypoglycaemia treatment?"},
    {"doc": "inpatient_glucose_management", "suite": "paraphrase", "q": "What blood sugar level counts as too low for a diabetic on the ward?"},
    {"doc": "pressure_injury_prevention", "suite": "keyword", "q": "What is the pressure injury prevention bundle and Braden score?"},
    {"doc": "pressure_injury_prevention", "suite": "paraphrase", "q": "How often should a bed-bound patient be turned to avoid bed sores?"},
    {"doc": "blood_transfusion_policy", "suite": "keyword", "q": "What is the haemoglobin threshold in the blood transfusion policy?"},
    {"doc": "blood_transfusion_policy", "suite": "paraphrase", "q": "The patient gets a fever and rash while receiving a unit of red cells - what should the nurse do?"},
    {"doc": "bed_management_surge_policy", "suite": "keyword", "q": "What are the bed management surge escalation levels?"},
    {"doc": "bed_management_surge_policy", "suite": "paraphrase", "q": "The hospital is almost full - when do we cancel planned operations?"},
    {"doc": "equipment_maintenance_policy", "suite": "keyword", "q": "What is the preventive maintenance interval for medical equipment?"},
    {"doc": "equipment_maintenance_policy", "suite": "paraphrase", "q": "How often does the MRI machine get serviced, and what if it is late?"},
    {"doc": "information_security_policy", "suite": "keyword", "q": "What is the password and account lockout policy?"},
    {"doc": "information_security_policy", "suite": "paraphrase", "q": "Can we put the API key directly in the code repository?"},
    {"doc": "data_retention_incident_policy", "suite": "keyword", "q": "What is the data retention and security incident response policy?"},
    {"doc": "data_retention_incident_policy", "suite": "paraphrase", "q": "A laptop with patient records was stolen - who do we tell and by when?"},
    {"doc": "antimicrobial_stewardship_policy", "suite": "keyword", "q": "What does the antimicrobial stewardship policy require at 48-72 hours?"},
    {"doc": "antimicrobial_stewardship_policy", "suite": "paraphrase", "q": "Can a doctor start meropenem without asking anyone?"},
    # Exact identifiers and figures: where keyword search should beat meaning search
    {"doc": "data_retention_incident_policy", "suite": "exact", "q": "POL-IT-002"},
    {"doc": "pressure_injury_prevention", "suite": "exact", "q": "CPG-CLIN-009"},
    {"doc": "sample_handling_policy", "suite": "exact", "q": "POL-LAB-001"},
    {"doc": "medication_storage_policy", "suite": "exact", "q": "POL-PHARM-001"},
    {"doc": "antimicrobial_stewardship_policy", "suite": "exact", "q": "linezolid colistin approval"},
    {"doc": "sepsis_screening_protocol", "suite": "exact", "q": "lactate 4 mmol/L"},
    {"doc": "blood_transfusion_policy", "suite": "exact", "q": "haemoglobin 70 g/L"},
    {"doc": "information_security_policy", "suite": "exact", "q": "POL-IT-001 lockout 5 attempts"},
    # Out of scope: the right answer is to find nothing
    {"doc": "", "suite": "out_scope", "q": "What will the weather be in Boston tomorrow?"},
    {"doc": "", "suite": "out_scope", "q": "Who won the football world cup in 2022?"},
    {"doc": "", "suite": "out_scope", "q": "Write me a poem about the ocean."},
    {"doc": "", "suite": "out_scope", "q": "What is the best recipe for chocolate cake?"},
    {"doc": "", "suite": "out_scope", "q": "How do I invest in cryptocurrency safely?"},
    {"doc": "", "suite": "out_scope", "q": "What is the capital city of Australia?"},
]

RESULTS_PATH = CACHE_DIR / "benchmark_results.json"


def evaluate(index: HybridIndex, mode: str) -> Dict[str, Any]:
    per_suite: Dict[str, Dict[str, float]] = {}
    rows = []
    started = time.perf_counter()
    for c in CASES:
        hits = index.search(c["q"], k=3, mode=mode)
        docs = [h.chunk.doc_id for h in hits]
        if c["suite"] == "out_scope":
            ok = not hits
            rows.append({"suite": c["suite"], "q": c["q"], "expected": None, "got": docs, "abstained_correctly": ok})
            s = per_suite.setdefault("out_scope", {"n": 0, "abstain": 0})
            s["n"] += 1
            s["abstain"] += ok
            continue
        rank = docs.index(c["doc"]) + 1 if c["doc"] in docs else None
        rows.append({"suite": c["suite"], "q": c["q"], "expected": c["doc"], "got": docs, "rank": rank})
        s = per_suite.setdefault(c["suite"], {"n": 0, "hit1": 0, "hit3": 0, "mrr": 0.0, "refused": 0})
        s["n"] += 1
        s["hit1"] += rank == 1
        s["hit3"] += rank is not None
        s["mrr"] += 1 / rank if rank else 0
        s["refused"] += not hits
    summary = {}
    for name, s in per_suite.items():
        if name == "out_scope":
            summary[name] = {"questions": s["n"], "abstained_pct": round(s["abstain"] / s["n"] * 100, 1)}
        else:
            summary[name] = {"questions": s["n"], "hit1_pct": round(s["hit1"] / s["n"] * 100, 1), "hit3_pct": round(s["hit3"] / s["n"] * 100, 1),
                             "mrr": round(s["mrr"] / s["n"], 3), "false_refusal_pct": round(s["refused"] / s["n"] * 100, 1)}
    return {"mode": mode, "summary": summary, "avg_latency_ms": round((time.perf_counter() - started) / len(CASES) * 1000, 1), "rows": rows}


def run_benchmark(index: HybridIndex = None) -> Dict[str, Any]:
    index = index or get_index()
    result = {
        "run_at": datetime.now().isoformat(timespec="seconds"), "dense_model": index.dense_label, "dense_error": index.dense_error,
        "documents": len({c.doc_id for c in index.chunks}), "chunks": len(index.chunks), "questions": len(CASES),
        "modes": [evaluate(index, m) for m in ("bm25", "dense", "hybrid")],
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def last_results() -> Dict[str, Any]:
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8")) if RESULTS_PATH.exists() else {}
