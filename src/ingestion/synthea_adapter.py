"""
Synthea Source Adapter for MediNexus AI.

Converts a Synthea CSV export (https://synthetichealth.github.io/synthea/) into the
12 raw MediNexus source tables consumed by the Bronze ingestion layer.

Clinical facts (patients, inpatient stays, diagnoses, labs, prescriptions, costs,
deaths, ICU stays, ventilation) come straight from Synthea. Synthea does not model a
few operational fields; those are simulated and listed in SIMULATED_FIELDS so they are
never mistaken for source data. Outcome labels (readmission, COVID outcomes) are NOT
created here - they are derived downstream in the Gold layer from event dates.
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import duckdb

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import RAW_DATA_DIR, METADATA_DIR, SYNTHEA_CSV_DIR, DATA_DIR
from src.ingestion.ingestion_utils import inject_realistic_imperfections
from src.utils.logging_utils import get_logger

logger = get_logger("synthea_adapter")

# Fields Synthea does not provide; generated here and documented in metadata.
SIMULATED_FIELDS = {
    "patients": ["blood_group", "contact", "emergency_contact"],
    "admissions": ["room_number"],
    "appointments": ["waiting_time_minutes", "No-Show/Cancelled rows (is_simulated=1)"],
    "billing": ["payment_status"],
    "pharmacy_inventory": ["stock_quantity", "batch_number", "expiry_date", "last_restocked_date (all sized from real prescription demand)"],
}

# SNOMED-CT -> ICD-10-CM crosswalk for the conditions present in Synthea, with a clinical severity tier.
SNOMED_TO_ICD10 = {
    "840539006": ("U07.1", "Severe"),       # COVID-19
    "840544004": ("Z20.828", "Mild"),       # Suspected COVID-19
    "59621000": ("I10", "Moderate"),        # Hypertension
    "44054006": ("E11.9", "Moderate"),      # Diabetes (type 2)
    "15777000": ("R73.03", "Mild"),         # Prediabetes
    "80394007": ("R73.9", "Mild"),          # Hyperglycemia
    "237602007": ("E88.81", "Moderate"),    # Metabolic syndrome X
    "55822004": ("E78.5", "Mild"),          # Hyperlipidemia
    "302870006": ("E78.1", "Mild"),         # Hypertriglyceridemia
    "162864005": ("E66.9", "Moderate"),     # BMI 30+ obesity
    "408512008": ("E66.01", "Severe"),      # BMI 40+ severe obesity
    "88805009": ("I50.9", "Severe"),        # Chronic congestive heart failure
    "84114007": ("I50.9", "Severe"),        # Heart failure
    "53741008": ("I25.10", "Severe"),       # Coronary heart disease
    "22298006": ("I21.9", "Severe"),        # Myocardial infarction
    "399211009": ("I25.2", "Moderate"),     # History of myocardial infarction
    "49436004": ("I48.91", "Moderate"),     # Atrial fibrillation
    "410429000": ("I46.9", "Severe"),       # Cardiac arrest
    "429007001": ("Z86.74", "Moderate"),    # History of cardiac arrest
    "230690007": ("I63.9", "Severe"),       # Stroke
    "86175003": ("I51.89", "Severe"),       # Injury of heart
    "87433001": ("J43.9", "Severe"),        # Pulmonary emphysema
    "185086009": ("J44.9", "Severe"),       # Chronic obstructive bronchitis
    "195967001": ("J45.909", "Moderate"),   # Asthma
    "233678006": ("J45.909", "Moderate"),   # Childhood asthma
    "233604007": ("J18.9", "Severe"),       # Pneumonia
    "65710008": ("J96.00", "Severe"),       # Acute respiratory failure
    "67782005": ("J80", "Severe"),          # ARDS
    "389087006": ("R09.02", "Moderate"),    # Hypoxemia
    "770349000": ("A41.89", "Severe"),      # Sepsis caused by virus
    "76571007": ("R65.21", "Severe"),       # Septic shock
    "706870000": ("I26.99", "Severe"),      # Acute pulmonary embolism
    "132281000119108": ("I82.409", "Severe"),  # Acute DVT
    "40095003": ("N17.9", "Severe"),        # Injury of kidney
    "234466008": ("D68.4", "Severe"),       # Acquired coagulation disorder
    "431855005": ("N18.1", "Moderate"),     # CKD stage 1
    "431856006": ("N18.2", "Moderate"),     # CKD stage 2
    "433144002": ("N18.3", "Severe"),       # CKD stage 3
    "127013003": ("E11.21", "Severe"),      # Diabetic renal disease
    "271737000": ("D64.9", "Moderate"),     # Anemia
    "26929004": ("G30.9", "Severe"),        # Alzheimer's disease
    "230265002": ("G30.0", "Severe"),       # Early-onset Alzheimer's
    "128613002": ("G40.909", "Moderate"),   # Seizure disorder
    "84757009": ("G40.909", "Moderate"),    # Epilepsy
    "254637007": ("C34.90", "Severe"),      # Non-small cell lung cancer
    "424132000": ("C34.90", "Severe"),      # NSCLC stage 1
    "254632001": ("C34.90", "Severe"),      # Small cell lung cancer
    "67811000119102": ("C34.90", "Severe"), # Small cell lung cancer stage 1
    "254837009": ("C50.919", "Severe"),     # Breast cancer
    "126906006": ("C61", "Severe"),         # Neoplasm of prostate
    "92691004": ("D07.5", "Moderate"),      # Carcinoma in situ of prostate
    "314994000": ("C79.9", "Severe"),       # Metastatic prostate cancer
    "363406005": ("C18.9", "Severe"),       # Malignant tumor of colon
    "109838007": ("C18.8", "Severe"),       # Overlapping malignant neoplasm of colon
    "94260004": ("C78.5", "Severe"),        # Secondary malignant neoplasm of colon
    "93761005": ("C18.9", "Severe"),        # Primary malignant neoplasm of colon
    "64859006": ("M81.0", "Moderate"),      # Osteoporosis
    "239873007": ("M17.9", "Mild"),         # Osteoarthritis of knee
    "239872002": ("M16.9", "Mild"),         # Osteoarthritis of hip
    "69896004": ("M06.9", "Moderate"),      # Rheumatoid arthritis
    "55680006": ("T50.901A", "Severe"),     # Drug overdose
    "5602001": ("F11.10", "Moderate"),      # Opioid abuse
    "7200002": ("F10.20", "Moderate"),      # Alcoholism
    "370143000": ("F32.9", "Moderate"),     # Major depression
    "74400008": ("K37", "Moderate"),        # Appendicitis
    "47693006": ("K35.32", "Severe"),       # Rupture of appendix
    "444814009": ("J01.90", "Mild"),        # Viral sinusitis
    "40055000": ("J32.9", "Mild"),          # Chronic sinusitis
    "195662009": ("J02.9", "Mild"),         # Acute viral pharyngitis
    "10509002": ("J20.9", "Mild"),          # Acute bronchitis
    "19169002": ("O03.9", "Moderate"),      # Miscarriage in first trimester
    "72892002": ("Z34.90", "Mild"),         # Normal pregnancy
    "449868002": ("F17.210", "Mild"),       # Smokes tobacco daily
}

# LOINC reference intervals (adult). crit_* = None means no critical threshold on that side.
LAB_REFERENCE = {
    # code: (test_name, category, low, high, crit_low, crit_high)
    "8480-6": ("Systolic Blood Pressure", "Vital Signs", 90, 120, 70, 180),
    "8462-4": ("Diastolic Blood Pressure", "Vital Signs", 60, 80, 40, 120),
    "8867-4": ("Heart Rate", "Vital Signs", 60, 100, 40, 130),
    "9279-1": ("Respiratory Rate", "Vital Signs", 12, 20, 8, 30),
    "2708-6": ("Oxygen Saturation (Arterial)", "Vital Signs", 95, 100, 88, None),
    "8310-5": ("Body Temperature", "Vital Signs", 36.1, 37.8, 35.0, 40.0),
    "39156-5": ("Body Mass Index", "Vital Signs", 18.5, 24.9, 15.0, 40.0),
    "2345-7": ("Glucose", "Chemistry", 70, 99, 50, 400),
    "2339-0": ("Glucose", "Chemistry", 70, 99, 50, 400),
    "3094-0": ("Urea Nitrogen (BUN)", "Chemistry", 7, 20, None, 100),
    "6299-2": ("Urea Nitrogen (BUN)", "Chemistry", 7, 20, None, 100),
    "2160-0": ("Creatinine", "Chemistry", 0.6, 1.3, None, 5.0),
    "38483-4": ("Creatinine", "Chemistry", 0.6, 1.3, None, 5.0),
    "17861-6": ("Calcium", "Chemistry", 8.5, 10.2, 6.5, 13.0),
    "49765-1": ("Calcium", "Chemistry", 8.5, 10.2, 6.5, 13.0),
    "2951-2": ("Sodium", "Chemistry", 135, 145, 120, 160),
    "2947-0": ("Sodium", "Chemistry", 135, 145, 120, 160),
    "2823-3": ("Potassium", "Chemistry", 3.5, 5.1, 2.5, 6.5),
    "6298-4": ("Potassium", "Chemistry", 3.5, 5.1, 2.5, 6.5),
    "2075-0": ("Chloride", "Chemistry", 98, 107, 80, 120),
    "2069-3": ("Chloride", "Chemistry", 98, 107, 80, 120),
    "2028-9": ("Carbon Dioxide", "Chemistry", 22, 29, 10, 40),
    "20565-8": ("Carbon Dioxide", "Chemistry", 22, 29, 10, 40),
    "33914-3": ("eGFR", "Chemistry", 60, 120, 15, None),
    "2885-2": ("Total Protein", "Liver Function", 6.0, 8.3, None, None),
    "1751-7": ("Albumin", "Liver Function", 3.5, 5.0, 1.5, None),
    "6768-6": ("Alkaline Phosphatase", "Liver Function", 44, 147, None, None),
    "1920-8": ("AST", "Liver Function", 10, 40, None, 1000),
    "1742-6": ("ALT", "Liver Function", 7, 56, None, 1000),
    "1975-2": ("Total Bilirubin", "Liver Function", 0.1, 1.2, None, 15.0),
    "718-7": ("Hemoglobin", "Hematology", 12.0, 17.5, 7.0, 20.0),
    "4544-3": ("Hematocrit", "Hematology", 36, 50, 21, 60),
    "6690-2": ("White Blood Cell Count", "Hematology", 4.5, 11.0, 2.0, 30.0),
    "777-3": ("Platelet Count", "Hematology", 150, 450, 50, 1000),
    "789-8": ("Red Blood Cell Count", "Hematology", 4.2, 5.9, None, None),
    "787-2": ("MCV", "Hematology", 80, 100, None, None),
    "785-6": ("MCH", "Hematology", 27, 33, None, None),
    "786-4": ("MCHC", "Hematology", 32, 36, None, None),
    "788-0": ("RDW", "Hematology", 11.5, 14.5, None, None),
    "731-0": ("Lymphocyte Count", "Hematology", 1.0, 4.8, 0.5, None),
    "751-8": ("Neutrophil Count", "Hematology", 1.8, 7.7, 0.5, None),
    "48065-7": ("D-Dimer", "Coagulation", 0.0, 0.5, None, 5.0),
    "5902-2": ("Prothrombin Time", "Coagulation", 11.0, 13.5, None, 30.0),
    "6301-6": ("INR", "Coagulation", 0.8, 1.1, None, 5.0),
    "1988-5": ("C-Reactive Protein", "Inflammatory Markers", 0.0, 10.0, None, 100.0),
    "2276-4": ("Ferritin", "Inflammatory Markers", 20, 300, None, 1000),
    "33959-8": ("Procalcitonin", "Inflammatory Markers", 0.0, 0.5, None, 2.0),
    "14804-9": ("Lactate Dehydrogenase", "Inflammatory Markers", 140, 280, None, 1000),
    "89579-7": ("Troponin I (hs)", "Cardiac", 0.0, 14.0, None, 100.0),
    "2157-6": ("Creatine Kinase", "Cardiac", 22, 198, None, 5000),
    "2093-3": ("Total Cholesterol", "Lipid", 125, 200, None, 400),
    "18262-6": ("LDL Cholesterol", "Lipid", 0, 100, None, 300),
    "2085-9": ("HDL Cholesterol", "Lipid", 40, 100, None, None),
    "2571-8": ("Triglycerides", "Lipid", 0, 150, None, 1000),
    "4548-4": ("HbA1c", "Endocrine", 4.0, 5.6, None, 14.0),
    "2744-1": ("pH (Arterial)", "Blood Gas", 7.35, 7.45, 7.2, 7.6),
    "2019-8": ("pCO2 (Arterial)", "Blood Gas", 35, 45, 20, 70),
    "2703-7": ("pO2 (Arterial)", "Blood Gas", 75, 100, 50, None),
    "1960-4": ("Bicarbonate (Arterial)", "Blood Gas", 22, 26, 10, 40),
}

# Ordered keyword rules: first match wins.
REASON_TO_DEPARTMENT = [
    (r"intensive care", "Critical Care"),
    (r"neoplasm|cancer|carcinoma|malignant|tumor|metasta", "Oncology"),
    (r"covid|isolation|pneumonia|respirat|asthma|emphysema|bronch|pulmonary|lung", "Pulmonology"),
    (r"heart|cardiac|myocard|coronary|atrial|stroke", "Cardiology"),
    (r"migraine|seizure|epilep|alzheimer|neuro|brain|concussion", "Neurology"),
    (r"fracture|sprain|tendon|ligament|orthop|osteo|arthr|menisc|whiplash", "Orthopedics"),
    (r"pregnan|obstet|gynec|antenatal|miscarr|eclampsia|ovum|fetus", "Obstetrics & Gynecology"),
    (r"drug|detox|rehab|overdose|opioid|alcohol|suicide|psych|depress", "Behavioral Health"),
    (r"appendic|surgical|surgery|molars|cholecyst|chole", "General Surgery"),
    (r"renal|kidney|dialysis", "Nephrology"),
]

SPECIALITY_TO_DEPARTMENT = [
    (r"CRITICAL CARE", "Critical Care"),
    (r"ONCOLOG|HEMATOLOG", "Oncology"),
    (r"PULMON|SLEEP", "Pulmonology"),
    (r"CARDI|VASCULAR|HEART", "Cardiology"),
    (r"NEURO", "Neurology"),
    (r"ORTHOP|PHYSICAL THERAPY|SPORTS|HAND SURGERY|PHYSICAL MEDICINE|CHIROPRACTIC|PODIATRY", "Orthopedics"),
    (r"OBSTET|GYNEC|MIDWIFE", "Obstetrics & Gynecology"),
    (r"PSYCH|SOCIAL WORKER|ADDICTION", "Behavioral Health"),
    (r"SURG", "General Surgery"),
    (r"NEPHRO", "Nephrology"),
    (r"EMERGENCY", "Emergency Medicine"),
    (r"RADIOLOG|NUCLEAR", "Radiology"),
    (r"PEDIATR", "Pediatrics"),
]

SPECIALITY_TO_QUALIFICATION = [
    (r"NURSE PRACTITIONER|CLINICAL NURSE", "NP"),
    (r"PHYSICIAN ASSISTANT", "PA-C"),
    (r"SOCIAL WORKER", "LCSW"),
    (r"PSYCHOLOGIST", "PhD (Clinical Psychology)"),
    (r"PHYSICAL THERAPY", "DPT"),
    (r"OCCUPATIONAL THERAPY", "OTR/L"),
    (r"DENTIST|ORAL SURGERY|MAXILLOFACIAL", "DDS"),
    (r"OPTOMETRY", "OD"),
    (r"CHIROPRACTIC", "DC"),
    (r"PODIATRY", "DPM"),
    (r"DIETITIAN", "RDN"),
    (r"AUDIOLOGIST", "AuD"),
    (r"SPEECH", "CCC-SLP"),
    (r"NURSE ANESTHETIST", "CRNA"),
    (r"MIDWIFE", "CNM"),
    (r"OSTEOPATHIC", "DO"),
]

MED_CATEGORY_RULES = [
    (r"insulin|metformin|liraglutide", "Antidiabetic"),
    (r"hydrochlorothiazide|amlodipine|atenolol|olmesartan|chlorthalidone|verapamil|captopril|metoprolol|furosemide", "Antihypertensive / Cardiovascular"),
    (r"simvastatin|atorvastatin", "Statin"),
    (r"warfarin|enoxaparin|heparin|clopidogrel|alteplase|aspirin", "Anticoagulant / Antiplatelet"),
    (r"digoxin|nitroglycerin|amiodarone", "Cardiac"),
    (r"albuterol|fluticasone|salmeterol|dornase", "Respiratory"),
    (r"cisplatin|paclitaxel|docetaxel|etoposide|oxaliplatin|carboplatin|doxorubicin|epirubicin|cyclophosphamide|leucovorin|leuprolide|tamoxifen|anastrozole|letrozole|fulvestrant|palbociclib|ribociclib|verzenio|trastuzumab", "Oncology"),
    (r"remdesivir|tocilizumab|baricitinib|hydroxychloroquine|chloroquine|leronlimab|lenzilumab|anakinra|cd24fc|aviptadil|cm4620", "COVID-19 Therapy"),
    (r"amoxicillin|penicillin|cefuroxime|cefaclor|vancomycin|piperacillin|azithromycin|doxycycline|nitrofurantoin", "Antibiotic"),
    (r"oxycodone|hydrocodone|meperidine|fentanyl|morphine|remifentanil", "Opioid Analgesic"),
    (r"acetaminophen|ibuprofen|naproxen|pregabalin|duloxetine|milnacipran", "Analgesic"),
    (r"loratadine|cetirizine|fexofenadine|diphenhydramine|chlorpheniramine|astemizole|terfenadine|epinephrine", "Antihistamine / Allergy"),
    (r"donepezil|memantine|galantamine|tacrine", "Dementia"),
    (r"sertraline|fluoxetine|clonazepam|diazepam|atomoxetine|methylphenidate|carbamazepine", "Psychiatric / Neurologic"),
    (r"pack|nuvaring|mirena|liletta|kyleena|etonogestrel|medroxyprogesterone|norelgestromin|enovid", "Contraceptive"),
    (r"norepinephrine|vasopressin|propofol|midazolam|rocuronium|isoflurane|desflurane|atropine|sodium chloride|ondansetron", "Critical Care / Anesthesia"),
    (r"epoetin|ferrous|vitamin b 12", "Hematologic"),
    (r"levothyroxine", "Thyroid Hormone"),
]

MED_FORM_RULES = [
    (r"inhaler|inhalation|actuat", "Inhaler"),
    (r"injection|injectable|syringe|infusion|\biv\b|pen injector", "Injection"),
    (r"capsule", "Capsule"),
    (r"tablet", "Tablet"),
    (r"solution|suspension", "Oral Solution"),
    (r"patch|transdermal", "Transdermal Patch"),
    (r"spray", "Spray"),
    (r"pack|ring|intrauterine|implant", "Contraceptive Device"),
    (r"cream", "Topical"),
]


def _first_match(series: pd.Series, rules, default: str) -> pd.Series:
    """Map a text series through ordered regex rules (first match wins)."""
    out = pd.Series(default, index=series.index, dtype=object)
    text = series.fillna("").astype(str)
    assigned = pd.Series(False, index=series.index)
    for pattern, label in rules:
        hit = text.str.contains(pattern, case=False, regex=True) & ~assigned
        out[hit] = label
        assigned |= hit
    return out


def _strip_digits(series: pd.Series) -> pd.Series:
    """Synthea appends digits to generated names (e.g. 'Zachary691'); remove them."""
    return series.fillna("").astype(str).str.replace(r"\d+", "", regex=True).str.strip()


def _peak_census(df: pd.DataFrame, group_col: str) -> pd.Series:
    """Peak simultaneous inpatient count per group (sweep over admit/discharge events)."""
    starts = df[[group_col, "start_ts"]].rename(columns={"start_ts": "ts"}).assign(delta=1)
    ends = df[[group_col, "stop_ts"]].rename(columns={"stop_ts": "ts"}).assign(delta=-1)
    events = pd.concat([starts, ends]).sort_values([group_col, "ts", "delta"])
    events["census"] = events.groupby(group_col)["delta"].cumsum()
    return events.groupby(group_col)["census"].max()


def _archive_existing_raw(raw_dir: Path) -> Optional[Path]:
    """Move previous non-Synthea raw files aside so stale generator output is never re-ingested."""
    existing = [p for p in raw_dir.glob("*") if p.is_file()]
    if not existing:
        return None
    summary_path = METADATA_DIR / "generation_summary.json"
    if summary_path.exists():
        try:
            if json.loads(summary_path.read_text(encoding="utf-8")).get("source") == "synthea":
                return None  # previous Synthea conversion: same file names, simply overwritten
        except (ValueError, OSError):
            pass
    dest = DATA_DIR / "legacy_raw" / datetime.now().strftime("%Y%m%d_%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for p in existing:
        shutil.move(str(p), str(dest / p.name))
    logger.info(f"Archived {len(existing)} previous raw files to {dest}")
    return dest


def convert_synthea_to_raw(
    synthea_dir: Path = SYNTHEA_CSV_DIR,
    output_dir: Path = RAW_DATA_DIR,
    seed: int = 42,
    inject_defects: bool = True,
    archive_existing: bool = True,
) -> Dict[str, Any]:
    """
    Convert a Synthea CSV export into the MediNexus raw source tables.
    """
    synthea_dir = Path(synthea_dir)
    required = ["patients", "encounters", "conditions", "observations", "medications",
                "procedures", "devices", "organizations", "providers", "payers", "payer_transitions"]
    missing = [t for t in required if not (synthea_dir / f"{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Synthea export in {synthea_dir} is missing: {missing}")

    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    archived_to = _archive_existing_raw(output_dir) if archive_existing else None

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    for t in required:
        path = (synthea_dir / f"{t}.csv").as_posix()
        con.execute(f"CREATE VIEW s_{t} AS SELECT * FROM read_csv_auto('{path}', header=true, sample_size=-1)")

    data_end = pd.Timestamp(con.execute("SELECT max(STOP)::TIMESTAMP FROM s_encounters").fetchone()[0])
    logger.info(f"Converting Synthea export from {synthea_dir} (data through {data_end.date()})")

    # ------------------------------------------------------------------
    # Identity maps: readable IDs for patients and encounters
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE pmap AS
        SELECT Id AS src_id, 'P_' || lpad(CAST(row_number() OVER (ORDER BY BIRTHDATE, Id) AS VARCHAR), 5, '0') AS patient_id
        FROM s_patients
    """)
    con.execute("""
        CREATE TABLE enc AS
        SELECT e.Id AS src_id,
               CASE ENCOUNTERCLASS WHEN 'inpatient' THEN 'ADM' WHEN 'emergency' THEN 'ED'
                                   WHEN 'urgentcare' THEN 'UC' ELSE 'APT' END AS prefix,
               e.ENCOUNTERCLASS AS enc_class, p.patient_id, e.PATIENT AS src_patient,
               e.ORGANIZATION AS src_org, e.PROVIDER AS src_provider, e.PAYER AS src_payer,
               e.START::TIMESTAMP AS start_ts, e.STOP::TIMESTAMP AS stop_ts,
               e.DESCRIPTION AS description, e.REASONCODE AS reason_code, e.REASONDESCRIPTION AS reason_desc,
               e.BASE_ENCOUNTER_COST AS base_cost, e.TOTAL_CLAIM_COST AS claim_cost, e.PAYER_COVERAGE AS payer_coverage
        FROM s_encounters e JOIN pmap p ON p.src_id = e.PATIENT
    """)
    con.execute("""
        CREATE TABLE emap AS
        SELECT src_id, prefix || '_' || lpad(CAST(row_number() OVER (PARTITION BY prefix ORDER BY start_ts, src_id) AS VARCHAR), 7, '0') AS encounter_id
        FROM enc
    """)
    con.execute("CREATE TABLE enc2 AS SELECT e.*, m.encounter_id FROM enc e JOIN emap m USING (src_id)")

    # ------------------------------------------------------------------
    # Facilities (organizations) & clinicians (providers)
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE omap AS
        SELECT o.Id AS src_id, 'HOSP_' || lpad(CAST(row_number() OVER (ORDER BY o.NAME, o.Id) AS VARCHAR), 4, '0') AS hospital_id
        FROM s_organizations o
        WHERE o.Id IN (SELECT src_org FROM enc2) OR o.Id IN (SELECT ORGANIZATION FROM s_providers WHERE Id IN (SELECT src_provider FROM enc2))
    """)
    con.execute("""
        CREATE TABLE dmap AS
        SELECT Id AS src_id, 'DOC_' || lpad(CAST(row_number() OVER (ORDER BY NAME, Id) AS VARCHAR), 5, '0') AS doctor_id
        FROM s_providers WHERE Id IN (SELECT src_provider FROM enc2)
    """)

    # ------------------------------------------------------------------
    # ADMISSIONS (Synthea inpatient encounters)
    # ------------------------------------------------------------------
    df_adm = con.execute("""
        WITH inp AS (SELECT * FROM enc2 WHERE enc_class = 'inpatient'),
        ed AS (SELECT DISTINCT i.src_id FROM inp i JOIN enc2 e
               ON e.src_patient = i.src_patient AND e.enc_class = 'emergency'
              AND e.start_ts BETWEEN i.start_ts - INTERVAL 1 DAY AND i.start_ts + INTERVAL 1 HOUR),
        uc AS (SELECT DISTINCT i.src_id FROM inp i JOIN enc2 e
               ON e.src_patient = i.src_patient AND e.enc_class = 'urgentcare'
              AND e.start_ts BETWEEN i.start_ts - INTERVAL 1 DAY AND i.start_ts + INTERVAL 1 HOUR),
        xfer AS (SELECT DISTINCT i.src_id FROM inp i JOIN inp n
                 ON n.src_patient = i.src_patient AND n.src_id <> i.src_id
                AND n.start_ts BETWEEN i.stop_ts - INTERVAL 1 HOUR AND i.stop_ts + INTERVAL 1 DAY),
        vent AS (SELECT DISTINCT ENCOUNTER AS src_id FROM s_procedures
                 WHERE DESCRIPTION ILIKE '%endotracheal%' OR DESCRIPTION ILIKE '%controlled ventilation%'
                 UNION SELECT DISTINCT ENCOUNTER FROM s_devices WHERE DESCRIPTION ILIKE '%ventilator%')
        SELECT i.encounter_id AS admission_id, i.patient_id, o.hospital_id, d.doctor_id,
               i.start_ts, i.stop_ts,
               strftime(i.start_ts, '%Y-%m-%d') AS admission_date,
               strftime(i.stop_ts, '%Y-%m-%d') AS discharge_date,
               strftime(i.start_ts, '%Y-%m-%dT%H:%M:%S') AS admission_datetime,
               strftime(i.stop_ts, '%Y-%m-%dT%H:%M:%S') AS discharge_datetime,
               date_diff('day', i.start_ts::DATE, i.stop_ts::DATE) AS length_of_stay,
               round(date_diff('minute', i.start_ts, i.stop_ts) / 60.0, 1) AS length_of_stay_hours,
               CASE WHEN i.src_id IN (SELECT src_id FROM ed) THEN 'Emergency'
                    WHEN i.src_id IN (SELECT src_id FROM uc) THEN 'Urgent' ELSE 'Elective' END AS admission_type,
               CASE WHEN p.DEATHDATE IS NOT NULL AND p.DEATHDATE BETWEEN i.start_ts::DATE AND i.stop_ts::DATE + 1 THEN 'Deceased'
                    WHEN i.src_id IN (SELECT src_id FROM xfer) THEN 'Transferred' ELSE 'Home' END AS discharge_disposition,
               coalesce(i.reason_desc, i.description) AS admission_reason,
               CAST(i.reason_code AS VARCHAR) AS admission_reason_code,
               i.description AS encounter_type,
               CAST(i.description ILIKE '%intensive care%' AS INTEGER) AS is_icu,
               CAST(i.src_id IN (SELECT src_id FROM vent) AS INTEGER) AS mechanical_ventilation,
               i.src_id AS _src_encounter
        FROM inp i
        JOIN s_patients p ON p.Id = i.src_patient
        LEFT JOIN omap o ON o.src_id = i.src_org
        LEFT JOIN dmap d ON d.src_id = i.src_provider
        ORDER BY i.start_ts
    """).df()
    df_adm["department_name"] = _first_match(df_adm["admission_reason"] + " " + df_adm["encounter_type"], REASON_TO_DEPARTMENT, "Internal Medicine")
    df_adm["room_number"] = rng.integers(101, 899, size=len(df_adm)).astype(str)  # simulated

    # ------------------------------------------------------------------
    # DOCTORS
    # ------------------------------------------------------------------
    df_doc = con.execute("""
        SELECT d.doctor_id, o.hospital_id, pr.NAME AS name, pr.SPECIALITY AS speciality_raw,
               pr.GENDER AS gender, pr.CITY AS city, pr.STATE AS state, pr.UTILIZATION AS encounter_volume
        FROM dmap d JOIN s_providers pr ON pr.Id = d.src_id
        LEFT JOIN omap o ON o.src_id = pr.ORGANIZATION
    """).df()
    df_doc["name"] = "Dr. " + _strip_digits(df_doc["name"])
    df_doc["specialty"] = df_doc["speciality_raw"].str.title()
    df_doc["qualification"] = _first_match(df_doc["speciality_raw"], SPECIALITY_TO_QUALIFICATION, "MD")
    df_doc["department_name"] = _first_match(df_doc["speciality_raw"], SPECIALITY_TO_DEPARTMENT, "Internal Medicine")
    df_doc["experience_years"] = np.nan  # not provided by Synthea; left unknown rather than invented

    # ------------------------------------------------------------------
    # HOSPITALS & DEPARTMENTS (bed capacity estimated from observed peak census)
    # ------------------------------------------------------------------
    df_hosp = con.execute("""
        SELECT m.hospital_id, o.NAME AS hospital_name, o.CITY || ', ' || o.STATE AS location,
               o.ADDRESS AS address, o.ZIP AS zip, o.LAT AS lat, o.LON AS lon,
               o.REVENUE AS reported_revenue, o.UTILIZATION AS encounter_volume
        FROM omap m JOIN s_organizations o ON o.Id = m.src_id
    """).df()
    adm_ts = df_adm.dropna(subset=["hospital_id"])
    peak_beds = _peak_census(adm_ts, "hospital_id")
    peak_icu = _peak_census(adm_ts[adm_ts["is_icu"] == 1], "hospital_id") if (adm_ts["is_icu"] == 1).any() else pd.Series(dtype=float)
    df_hosp["facility_type"] = np.where(df_hosp["hospital_id"].isin(peak_beds.index), "Hospital", "Clinic")
    df_hosp["total_beds"] = np.ceil(df_hosp["hospital_id"].map(peak_beds).fillna(0) * 1.25).astype(int)
    df_hosp["icu_beds"] = np.ceil(df_hosp["hospital_id"].map(peak_icu).fillna(0) * 1.25).astype(int)
    df_hosp["operational_status"] = "Active"

    adm_ts = adm_ts.assign(_dept_key=adm_ts["hospital_id"] + "|" + adm_ts["department_name"])
    peak_dept = _peak_census(adm_ts, "_dept_key")
    dept_pairs = pd.concat([
        df_adm[["hospital_id", "department_name"]],
        df_doc[["hospital_id", "department_name"]],
    ]).dropna().drop_duplicates().sort_values(["hospital_id", "department_name"]).reset_index(drop=True)
    dept_pairs["department_id"] = [f"DEPT_{i + 1:05d}" for i in range(len(dept_pairs))]
    dept_pairs["bed_capacity"] = np.ceil(
        (dept_pairs["hospital_id"] + "|" + dept_pairs["department_name"]).map(peak_dept).fillna(0) * 1.25
    ).astype(int)
    df_dept = dept_pairs[["department_id", "hospital_id", "department_name", "bed_capacity"]]
    dept_lookup = df_dept.set_index(["hospital_id", "department_name"])["department_id"]

    df_adm["department_id"] = pd.MultiIndex.from_frame(df_adm[["hospital_id", "department_name"]]).map(dept_lookup)
    df_doc["department_id"] = pd.MultiIndex.from_frame(df_doc[["hospital_id", "department_name"]]).map(dept_lookup)

    # ------------------------------------------------------------------
    # PATIENTS
    # ------------------------------------------------------------------
    df_pat = con.execute(f"""
        WITH last_payer AS (
            SELECT PATIENT, PAYER FROM (
                SELECT PATIENT, PAYER, row_number() OVER (PARTITION BY PATIENT ORDER BY END_YEAR DESC, START_YEAR DESC) rn
                FROM s_payer_transitions) WHERE rn = 1),
        first_seen AS (SELECT src_patient, min(start_ts) AS first_ts FROM enc2 GROUP BY 1)
        SELECT m.patient_id, p.FIRST AS first_name, p.LAST AS last_name,
               strftime(p.BIRTHDATE, '%Y-%m-%d') AS dob,
               CAST(floor(date_diff('day', p.BIRTHDATE, coalesce(p.DEATHDATE, DATE '{data_end.date()}')) / 365.25) AS INTEGER) AS age,
               CASE p.GENDER WHEN 'M' THEN 'Male' WHEN 'F' THEN 'Female' ELSE 'Other' END AS gender,
               p.ADDRESS || ', ' || p.CITY AS address, p.CITY AS city, p.COUNTY AS county, p.STATE AS state,
               p.RACE AS race, p.ETHNICITY AS ethnicity, p.MARITAL AS marital_status,
               coalesce(py.NAME, 'NO_INSURANCE') AS insurance_provider,
               strftime(p.DEATHDATE, '%Y-%m-%d') AS death_date,
               CAST(p.DEATHDATE IS NOT NULL AS INTEGER) AS is_deceased,
               round(p.HEALTHCARE_EXPENSES, 2) AS healthcare_expenses,
               round(p.HEALTHCARE_COVERAGE, 2) AS healthcare_coverage,
               strftime(f.first_ts, '%Y-%m-%d') AS created_at,
               p.Id AS source_patient_id
        FROM pmap m JOIN s_patients p ON p.Id = m.src_id
        LEFT JOIN last_payer lp ON lp.PATIENT = p.Id
        LEFT JOIN s_payers py ON py.Id = lp.PAYER
        LEFT JOIN first_seen f ON f.src_patient = p.Id
        ORDER BY m.patient_id
    """).df()
    df_pat["name"] = _strip_digits(df_pat["first_name"]) + " " + _strip_digits(df_pat["last_name"])
    df_pat = df_pat.drop(columns=["first_name", "last_name"])
    n_pat = len(df_pat)
    # Simulated: Synthea has no blood type or phone numbers (US ABO/Rh distribution).
    df_pat["blood_group"] = rng.choice(["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"], size=n_pat,
                                       p=[0.374, 0.357, 0.085, 0.034, 0.066, 0.063, 0.015, 0.006])
    df_pat["contact"] = [f"+1-555-{a:03d}-{b:04d}" for a, b in zip(rng.integers(100, 999, n_pat), rng.integers(0, 9999, n_pat))]
    df_pat["emergency_contact"] = [f"+1-555-{a:03d}-{b:04d}" for a, b in zip(rng.integers(100, 999, n_pat), rng.integers(0, 9999, n_pat))]

    # ------------------------------------------------------------------
    # DIAGNOSES (all Synthea conditions, SNOMED + ICD-10 crosswalk)
    # ------------------------------------------------------------------
    df_dx = con.execute("""
        SELECT 'DX_' || lpad(CAST(row_number() OVER (ORDER BY c.START, e.encounter_id, c.CODE) AS VARCHAR), 7, '0') AS diagnosis_id,
               CASE WHEN e.enc_class = 'inpatient' THEN e.encounter_id END AS admission_id,
               e.encounter_id, m.patient_id,
               CAST(c.CODE AS VARCHAR) AS snomed_code, c.DESCRIPTION AS diagnosis_description,
               CASE WHEN CAST(e.reason_code AS VARCHAR) = CAST(c.CODE AS VARCHAR) THEN 'Primary' ELSE 'Secondary' END AS diagnosis_type,
               strftime(c.START, '%Y-%m-%d') AS diagnosis_date,
               strftime(c.STOP, '%Y-%m-%d') AS resolved_date
        FROM s_conditions c
        JOIN pmap m ON m.src_id = c.PATIENT
        LEFT JOIN enc2 e ON e.src_id = c.ENCOUNTER
    """).df()
    xwalk = pd.DataFrame([(k, v[0], v[1]) for k, v in SNOMED_TO_ICD10.items()], columns=["snomed_code", "icd10_code", "severity"])
    df_dx = df_dx.merge(xwalk, on="snomed_code", how="left")
    is_finding = df_dx["diagnosis_description"].str.contains(r"\((?:finding|situation)\)", regex=True, na=False)
    df_dx["severity"] = df_dx["severity"].fillna(pd.Series(np.where(is_finding, "Mild", "Moderate"), index=df_dx.index))

    # ------------------------------------------------------------------
    # LABORATORY RESULTS (numeric LOINC observations with reference intervals)
    # ------------------------------------------------------------------
    ref = pd.DataFrame(
        [(k, *v) for k, v in LAB_REFERENCE.items()],
        columns=["loinc_code", "test_name", "test_category", "low", "high", "crit_low", "crit_high"],
    )
    ref[["low", "high", "crit_low", "crit_high"]] = ref[["low", "high", "crit_low", "crit_high"]].astype(float)
    con.register("lab_ref", ref)
    df_lab = con.execute("""
        SELECT 'LAB_' || lpad(CAST(row_number() OVER (ORDER BY o."DATE", m.patient_id, o.CODE) AS VARCHAR), 8, '0') AS lab_id,
               m.patient_id,
               CASE WHEN e.enc_class = 'inpatient' THEN e.encounter_id END AS admission_id,
               e.encounter_id, CAST(o.CODE AS VARCHAR) AS loinc_code,
               r.test_name, r.test_category,
               round(try_cast(o.VALUE AS DOUBLE), 2) AS test_value,
               o.UNITS AS unit,
               strftime(o."DATE"::TIMESTAMP, '%Y-%m-%d') AS test_date,
               r.low, r.high, r.crit_low, r.crit_high
        FROM s_observations o
        JOIN lab_ref r ON r.loinc_code = CAST(o.CODE AS VARCHAR)
        JOIN pmap m ON m.src_id = o.PATIENT
        LEFT JOIN enc2 e ON e.src_id = o.ENCOUNTER
        WHERE try_cast(o.VALUE AS DOUBLE) IS NOT NULL
    """).df()
    v = df_lab["test_value"]
    crit = (df_lab["crit_low"].notna() & (v < df_lab["crit_low"])) | (df_lab["crit_high"].notna() & (v > df_lab["crit_high"]))
    df_lab["abnormal_flag"] = np.select(
        [crit, v < df_lab["low"], v > df_lab["high"]], ["Critical", "Low", "High"], default="Normal"
    )
    df_lab["reference_range"] = df_lab["low"].astype(str) + " - " + df_lab["high"].astype(str)
    df_lab = df_lab.drop(columns=["low", "high", "crit_low", "crit_high"])

    # ------------------------------------------------------------------
    # MEDICATIONS catalog & PRESCRIPTIONS
    # ------------------------------------------------------------------
    df_med = con.execute("""
        SELECT CAST(CODE AS VARCHAR) AS rxnorm_code, first(DESCRIPTION) AS medication_name,
               round(median(BASE_COST), 2) AS unit_cost, count(*) AS n_orders
        FROM s_medications GROUP BY 1 ORDER BY n_orders DESC
    """).df()
    df_med["medication_id"] = [f"MED_{i + 1:04d}" for i in range(len(df_med))]
    df_med["category"] = _first_match(df_med["medication_name"], MED_CATEGORY_RULES, "Other")
    df_med["dosage_form"] = _first_match(df_med["medication_name"], MED_FORM_RULES, "Other")
    strength = df_med["medication_name"].str.extract(r"(\d+(?:\.\d+)?)\s*MG", expand=False)
    df_med["standard_daily_dose"] = pd.to_numeric(strength, errors="coerce")  # strength per unit (mg) where stated
    con.register("med_cat", df_med[["rxnorm_code", "medication_id"]])

    df_rx = con.execute(f"""
        SELECT 'RX_' || lpad(CAST(row_number() OVER (ORDER BY md.START, m.patient_id, md.CODE) AS VARCHAR), 7, '0') AS prescription_id,
               m.patient_id, d.doctor_id, o.hospital_id,
               CASE WHEN e.enc_class = 'inpatient' THEN e.encounter_id END AS admission_id,
               e.encounter_id, mc.medication_id,
               regexp_extract(md.DESCRIPTION, '(\\d+(\\.\\d+)? ?(MG|UNT|MCG)(/ML)?)', 1) AS dosage,
               'Not recorded' AS frequency,
               greatest(date_diff('day', md.START::DATE, coalesce(md.STOP::TIMESTAMP, TIMESTAMP '{data_end}')::DATE), 1) AS duration_days,
               md.DISPENSES AS quantity,
               strftime(md.START::TIMESTAMP, '%Y-%m-%d') AS prescription_date,
               strftime(md.STOP::TIMESTAMP, '%Y-%m-%d') AS end_date,
               CASE WHEN md.STOP IS NULL OR md.STOP::TIMESTAMP > TIMESTAMP '{data_end}' THEN 'Active' ELSE 'Completed' END AS status,
               round(md.TOTALCOST, 2) AS total_cost,
               round(md.PAYER_COVERAGE, 2) AS payer_coverage,
               md.REASONDESCRIPTION AS indication
        FROM s_medications md
        JOIN pmap m ON m.src_id = md.PATIENT
        JOIN med_cat mc ON mc.rxnorm_code = CAST(md.CODE AS VARCHAR)
        LEFT JOIN enc2 e ON e.src_id = md.ENCOUNTER
        LEFT JOIN dmap d ON d.src_id = e.src_provider
        LEFT JOIN omap o ON o.src_id = e.src_org
    """).df()

    # Reorder threshold: 14 days of network-wide demand over the final year of data
    recent = df_rx[pd.to_datetime(df_rx["prescription_date"]) >= data_end - pd.Timedelta(days=365)]
    daily_net = recent.groupby("medication_id")["quantity"].sum() / 365.0
    df_med["reorder_threshold"] = np.ceil(df_med["medication_id"].map(daily_net).fillna(0) * 14).astype(int) + 5
    df_med = df_med[["medication_id", "rxnorm_code", "medication_name", "category", "dosage_form",
                     "unit_cost", "reorder_threshold", "standard_daily_dose", "n_orders"]]

    # ------------------------------------------------------------------
    # PHARMACY INVENTORY (simulated stock sized from real per-site demand)
    # ------------------------------------------------------------------
    # Stock only lines a site actually dispenses (>= ~1 unit/month over the final year)
    site_demand = (
        recent.dropna(subset=["hospital_id"])
        .groupby(["hospital_id", "medication_id"])["quantity"].sum().div(365.0).rename("daily").reset_index()
    )
    site_demand = site_demand[site_demand["daily"] >= 1 / 30].reset_index(drop=True)
    n_inv = len(site_demand)
    reorder_level = (np.ceil(site_demand["daily"] * 14) + 2).astype(int)  # 14-day safety stock
    cycle_stock = site_demand["daily"] * rng.lognormal(mean=np.log(25), sigma=0.6, size=n_inv)
    stock = np.round(reorder_level + cycle_stock)
    below = rng.random(n_inv) < 0.12  # sites that have drawn down past their reorder point
    stock = np.where(below, np.round(reorder_level * rng.uniform(0.1, 1.0, n_inv)), stock).astype(int)
    df_inv = pd.DataFrame({
        "inventory_id": [f"INV_{i + 1:06d}" for i in range(n_inv)],
        "medication_id": site_demand["medication_id"],
        "hospital_id": site_demand["hospital_id"],
        "stock_quantity": stock,
        "batch_number": [f"BATCH_{x}" for x in rng.integers(1000, 9999, n_inv)],
        "expiry_date": [(data_end + pd.Timedelta(days=int(x))).strftime("%Y-%m-%d") for x in rng.integers(60, 720, n_inv)],
        "reorder_level": reorder_level,
        "last_restocked_date": [(data_end - pd.Timedelta(days=int(x))).strftime("%Y-%m-%d") for x in rng.integers(1, 60, n_inv)],
    })

    # ------------------------------------------------------------------
    # APPOINTMENTS (real ambulatory/outpatient/wellness visits + simulated missed visits)
    # ------------------------------------------------------------------
    df_apt = con.execute("""
        SELECT e.encounter_id AS appointment_id, e.patient_id, d.doctor_id, o.hospital_id,
               strftime(e.start_ts, '%Y-%m-%d') AS appointment_date,
               strftime(e.start_ts, '%H:%M') AS appointment_time,
               'Completed' AS status,
               coalesce(e.reason_desc, e.description) AS reason_for_visit,
               e.enc_class AS visit_type,
               round(e.claim_cost, 2) AS visit_cost,
               0 AS is_simulated
        FROM enc2 e
        LEFT JOIN dmap d ON d.src_id = e.src_provider
        LEFT JOIN omap o ON o.src_id = e.src_org
        WHERE e.enc_class IN ('ambulatory', 'outpatient', 'wellness')
    """).df()
    doc_dept = df_doc.set_index("doctor_id")["department_id"]
    df_apt["department_id"] = df_apt["doctor_id"].map(doc_dept)
    df_apt["waiting_time_minutes"] = np.clip(rng.lognormal(np.log(18), 0.5, len(df_apt)), 0, 180).round().astype(int)  # simulated
    n_missed = int(len(df_apt) * 0.12)
    missed = df_apt.sample(n=n_missed, random_state=seed).copy()
    missed["appointment_id"] = [f"APT_S{i + 1:07d}" for i in range(n_missed)]
    missed["appointment_date"] = (pd.to_datetime(missed["appointment_date"]) + pd.to_timedelta(rng.integers(-14, 14, n_missed), unit="D")).dt.strftime("%Y-%m-%d")
    missed["status"] = rng.choice(["No-Show", "Cancelled"], size=n_missed, p=[0.45, 0.55])
    missed["waiting_time_minutes"] = 0
    missed["visit_cost"] = 0.0
    missed["is_simulated"] = 1
    df_apt = pd.concat([df_apt, missed], ignore_index=True).sort_values("appointment_date", ignore_index=True)

    # ------------------------------------------------------------------
    # BILLING (one claim per admission: encounter + procedures + medications)
    # ------------------------------------------------------------------
    df_bill = con.execute("""
        WITH proc AS (SELECT ENCOUNTER, sum(BASE_COST) AS proc_cost FROM s_procedures GROUP BY 1),
        meds AS (SELECT ENCOUNTER, sum(TOTALCOST) AS med_cost, sum(PAYER_COVERAGE) AS med_cov FROM s_medications GROUP BY 1)
        SELECT e.encounter_id AS admission_id, e.patient_id,
               strftime(e.stop_ts, '%Y-%m-%d') AS bill_date,
               e.claim_cost, e.payer_coverage, coalesce(p.proc_cost, 0) AS proc_cost,
               coalesce(m.med_cost, 0) AS med_cost, coalesce(m.med_cov, 0) AS med_cov,
               coalesce(py.NAME, 'NO_INSURANCE') AS payer_name
        FROM enc2 e
        LEFT JOIN proc p ON p.ENCOUNTER = e.src_id
        LEFT JOIN meds m ON m.ENCOUNTER = e.src_id
        LEFT JOIN s_payers py ON py.Id = e.src_payer
        WHERE e.enc_class = 'inpatient'
        ORDER BY e.start_ts
    """).df()
    enc_ratio = np.where(df_bill["claim_cost"] > 0, df_bill["payer_coverage"] / df_bill["claim_cost"], 0.0)
    df_bill["total_amount"] = (df_bill["claim_cost"] + df_bill["proc_cost"] + df_bill["med_cost"]).round(2)
    df_bill["insurance_covered"] = (df_bill["payer_coverage"] + df_bill["med_cov"] + df_bill["proc_cost"] * enc_ratio).round(2)
    df_bill["insurance_covered"] = np.minimum(df_bill["insurance_covered"], df_bill["total_amount"])
    df_bill["patient_payable"] = (df_bill["total_amount"] - df_bill["insurance_covered"]).round(2)
    df_bill["payment_method"] = np.where(df_bill["payer_name"] == "NO_INSURANCE", "Self-Pay", df_bill["payer_name"])
    owes = df_bill["patient_payable"] > 1.0
    df_bill["payment_status"] = np.where(  # simulated
        owes, rng.choice(["Paid", "Pending", "Overdue"], size=len(df_bill), p=[0.72, 0.20, 0.08]), "Paid"
    )
    df_bill.insert(0, "bill_id", [f"BILL_{i + 1:06d}" for i in range(len(df_bill))])
    df_bill = df_bill[["bill_id", "patient_id", "admission_id", "bill_date", "total_amount", "insurance_covered",
                       "patient_payable", "payment_status", "payment_method", "proc_cost", "med_cost"]]

    df_adm = df_adm.drop(columns=["start_ts", "stop_ts", "_src_encounter"])
    df_hosp = df_hosp[["hospital_id", "hospital_name", "location", "total_beds", "icu_beds", "operational_status",
                       "facility_type", "address", "zip", "lat", "lon", "reported_revenue", "encounter_volume"]]
    df_doc = df_doc[["doctor_id", "hospital_id", "department_id", "name", "specialty", "qualification",
                     "experience_years", "gender", "city", "state", "encounter_volume"]]
    con.close()

    # ------------------------------------------------------------------
    # Realistic source-system defects for the Bronze -> Silver cleansing story
    # ------------------------------------------------------------------
    if inject_defects:
        logger.info("Injecting source-system data quality defects...")
        df_pat = inject_realistic_imperfections(df_pat, ["dob", "created_at"], ["gender", "blood_group"],
                                                ["contact", "emergency_contact", "address"], ["age"], 0.015, seed)
        df_adm = inject_realistic_imperfections(df_adm, ["admission_date", "discharge_date"],
                                                ["admission_type", "discharge_disposition"], ["room_number"],
                                                ["length_of_stay"], 0.012, seed + 1)
        df_dx = inject_realistic_imperfections(df_dx, ["diagnosis_date"], ["severity", "diagnosis_type"], [], None, 0.01, seed + 2)
        df_lab = inject_realistic_imperfections(df_lab, ["test_date"], ["abnormal_flag"], ["unit"], ["test_value"], 0.01, seed + 3)
        df_med = inject_realistic_imperfections(df_med, None, ["category"], ["dosage_form"], None, 0.0, seed + 4)
        df_rx = inject_realistic_imperfections(df_rx, ["prescription_date"], ["status"], ["dosage"], None, 0.01, seed + 5)
        df_apt = inject_realistic_imperfections(df_apt, ["appointment_date"], ["status"], ["reason_for_visit"], None, 0.01, seed + 6)
        df_bill = inject_realistic_imperfections(df_bill, ["bill_date"], ["payment_status", "payment_method"],
                                                 ["payment_method"], None, 0.01, seed + 7)
        df_inv = inject_realistic_imperfections(df_inv, ["expiry_date", "last_restocked_date"], [], ["batch_number"], None, 0.01, seed + 8)

    # ------------------------------------------------------------------
    # Persist (multi-format: CSV EHR extracts, JSON catalog, Parquet analyzer feed)
    # ------------------------------------------------------------------
    logger.info(f"Writing raw source files to {output_dir}...")
    df_hosp.to_csv(output_dir / "hospitals.csv", index=False)
    df_dept.to_csv(output_dir / "departments.csv", index=False)
    df_doc.to_csv(output_dir / "doctors.csv", index=False)
    df_pat.to_csv(output_dir / "patients.csv", index=False)
    df_adm.to_csv(output_dir / "admissions.csv", index=False)
    df_dx.to_csv(output_dir / "diagnoses.csv", index=False)
    df_rx.to_csv(output_dir / "prescriptions.csv", index=False)
    df_apt.to_csv(output_dir / "appointments.csv", index=False)
    df_bill.to_csv(output_dir / "billing.csv", index=False)
    df_inv.to_csv(output_dir / "pharmacy_inventory.csv", index=False)
    df_med.to_json(output_dir / "medications.json", orient="records")
    df_lab.to_parquet(output_dir / "laboratory_results.parquet", index=False)

    counts = {
        "hospitals": len(df_hosp), "departments": len(df_dept), "doctors": len(df_doc),
        "patients": len(df_pat), "admissions": len(df_adm), "diagnoses": len(df_dx),
        "laboratory_results": len(df_lab), "medications": len(df_med), "prescriptions": len(df_rx),
        "appointments": len(df_apt), "billing": len(df_bill), "pharmacy_inventory": len(df_inv),
    }
    summary = {
        "generated_at": datetime.now().isoformat(),
        "source": "synthea",
        "source_dir": str(synthea_dir),
        "data_through": str(data_end.date()),
        "seed": seed,
        "counts": counts,
        "simulated_fields": SIMULATED_FIELDS,
        "derived_downstream": ["readmitted_30d (Gold, from admission dates)", "COVID-19 outcomes (Gold, from event dates)"],
        "quality_defects_injected": [
            "Intentional duplicate rows (~1-1.5%)",
            "Inconsistent date representations (MM/DD/YYYY, DD-MM-YYYY, ISO)",
            "Irregular casing (UPPER, lower, leading/trailing whitespace)",
            "Missing values in optional fields (~3%)",
            "Invalid categorical token anomalies ('UNKNOWN_VAL')",
            "Occasional invalid numerical values for outlier detection",
        ] if inject_defects else [],
        "archived_previous_raw_to": str(archived_to) if archived_to else None,
    }
    with open(METADATA_DIR / "generation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Synthea conversion complete. Total records: {sum(counts.values()):,}")
    return summary


if __name__ == "__main__":
    convert_synthea_to_raw()
