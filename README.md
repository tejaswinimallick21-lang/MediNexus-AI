# MediNexus AI — Role-Based Healthcare Data-to-Decision Intelligence Platform

[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![Lakehouse](https://img.shields.io/badge/Lakehouse-Medallion%20(Bronze%2FSilver%2FGold)-teal)](https://duckdb.org/)
[![RBAC Security](https://img.shields.io/badge/Security-Strict%20RBAC%20%26%20Audit-red)](https://github.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Healthcare%20Demo-green)](https://github.com/)

---

## 1. Project Overview
**MediNexus AI** is a role-aware clinical and operational decision intelligence platform. It ingests fragmented, heterogeneous healthcare data, runs it through an automated, quality-audited **Medallion Architecture (Bronze ➔ Silver ➔ Gold)**, trains predictive machine learning models, applies prescriptive clinical and operational rules, and serves role-tailored decision consoles to seven distinct healthcare stakeholders.

The core pipeline represents the journey:
### **DATA ➔ TRUST ➔ INTELLIGENCE ➔ PREDICTION ➔ PRESCRIPTION ➔ ACTION**

---

## 2. Real-World Problem Statement
Healthcare ecosystems generate massive volumes of heterogeneous data across Electronic Health Records (EHR), laboratory analyzers, pharmacy inventories, computerized provider order entries (CPOE), scheduling systems, and financial billing engines. In practice, this data suffers from:
* Severe fragmentation across relational databases, CSV exports, and JSON feeds.
* Systematic data quality degradation (missing demographics, duplicated encounter records, unstandardized ICD-10 codings, conflicting date formats, and out-of-range clinical measurements).
* **Information Mismatch**: Front-desk coordinators, attending physicians, hospital chief executives, clinical pharmacists, and pathology specialists each require fundamentally distinct views of the same patient journey. Exposing raw tables or generic dashboards results in cognitive overload, privacy breaches, and unmitigated clinical risk.

---

## 3. Proposed Solution
MediNexus AI decouples the **Data Engineering / Producer Layer** from the **Consumption / Business Layer**:
1. **Producer Layer**: Ingests multi-format source data into Bronze Parquet, applies deterministic deduplication, type validation, date parsing, anomaly repair, and quality scoring into Silver, and materializes high-dimensional, business-ready joined analytical models in Gold.
2. **Consumption Layer**: Business users consume **strictly validated GOLD models**. Front-end business dashboards are barred from manipulating raw or bronze data directly.
3. **Role-Aware Decision Consoles**: Tailored dashboards for 7 personas with embedded predictive ML, prescriptive care checklists, and specialized AI copilot agents.

---

## 4. Platform Novelty
The novelty of MediNexus AI is **NOT** simply using Streamlit, DuckDB, or Random Forests. 

The novelty is the **Role-Aware Data-to-Decision Pipeline**:
* A single underlying healthcare ecosystem is ingested once, audited against rigorous completeness and uniqueness indices, and modeled into a unified Gold layer.
* The system then drives completely different, role-calibrated actions:
  * For the **Doctor**: Predicts individual 30-day readmission risk, explains contributing biomarkers, and prescribes targeted transitional care plans.
  * For the **Pharmacist**: Evaluates inventory burn rate, forecasts 30-day medication demand, and issues electronic replenishment purchase orders.
  * For the **Laboratory Specialist**: Monitors automated chemistry throughput, isolates life-critical test alarms, and forecasts analyzer bench staffing needs.
  * For the **Hospital Administrator**: Models bed occupancy rates, investigates root causes of readmissions, and triggers hospital surge capacity directives.
  * For the **Receptionist**: Tracks outpatient appointment flows and wait times while strictly redacting clinical diagnoses under privacy compliance.

---

## 5. Data Source: Synthea
The platform runs on the **Synthea COVID-19 10K CSV export** (12,352 synthetic Massachusetts patients, 321k encounters, 9,584 inpatient stays across 91 hospitals, 1.2M lab/vital results, data through 2020-05-27) from https://synthetichealth.github.io/synthea/downloads.html. Synthea simulates full patient lifetimes from clinical disease models, so diagnoses, labs, medications, stays, costs and deaths are linked the way they are in real records.

`src/ingestion/synthea_adapter.py` maps the Synthea tables onto the 12 raw MediNexus source tables (SNOMED→ICD-10 crosswalk, LOINC reference ranges, encounter/claim cost roll-ups) and injects source-system defects for the Silver layer to repair.

* **Taken from Synthea:** demographics, deaths, admissions & timestamps, ICU stays, mechanical ventilation, diagnoses, labs/vitals, prescriptions, costs & payers, hospitals, clinicians.
* **Simulated (Synthea has no equivalent):** blood group, phone numbers, room numbers, appointment wait times and missed visits (`is_simulated=1`), payment status, pharmacy stock levels (sized from real dispensing demand). Listed in `data/metadata/generation_summary.json`.
* **Derived in Gold from event dates (never generated):** unplanned 30-day readmission and COVID-19 outcomes.
* **Bed capacity** is estimated as 1.25× each unit's observed peak census, so occupancy rates are relative, not reported capacity.

Setup: download `10k_synthea_covid19_csv.zip` (≈54 MB) and extract its CSVs into `data/synthea/csv/`. To scale up, point `SYNTHEA_CSV_DIR` in `config/constants.py` at the 100K export (same schema). The legacy Faker generator (`src/ingestion/generate_datasets.py`) is only used when no Synthea export is present.

> Please cite: Walonoski J, et al. *Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record.* JAMIA 2018;25(3):230–238.

---

## 6. Medallion Lakehouse Architecture
```
RAW DATA SOURCES (CSV, JSON, Parquet)
│   (Intentional Duplicates, Missing Values, Format Inconsistencies)
▼
BRONZE LAYER (data/bronze/*.parquet)
│   - Source fidelity preserved without structural alteration
│   - Metadata columns added: _bronze_ingested_at, _bronze_run_id, _bronze_source_file
│   - DuckDB table: ingestion_runs metadata logging
▼
SILVER LAYER (data/silver/*.parquet)
│   - Deduplication on primary keys (patient_id, admission_id, lab_id, etc.)
│   - ISO-8601 date harmonization (MM/DD/YYYY, DD-MM-YYYY ➔ YYYY-MM-DD)
│   - Domain categorical normalization (Title casing, standard gender/blood group codes)
│   - Numeric bounding & outlier clipping (e.g. Length of stay, positive ages)
│   - Referential integrity checks between foreign and primary keys
│   - DuckDB table: silver_quality_report (Quality Score %, completeness, uniqueness)
▼
GOLD CONSUMPTION LAYER (data/gold/*.parquet)
│   - Business-ready joined dimensional models:
│     * gold_patient_360 (Comprehensive patient demographic, comorbidity, and encounter profile)
│     * gold_admissions (Inpatient stays with 30-day readmission targets and billing sums)
│     * gold_clinical (Diagnoses, ICD-10 codings, and clinical severity)
│     * gold_laboratory (Biomarkers, reference ranges, and critical alarm classifications)
│     * gold_pharmacy (Formulary stock, daily consumption burn, and days of supply)
│     * gold_prescriptions (Active and historical medications, dosages, and costs)
│     * gold_appointments (Outpatient visits, wait times, cancellations, and no-shows)
│     * gold_billing (Inpatient charges, insurance coverage, and patient balances)
│     * gold_hospital_operations (Occupancy rates, bed turnovers, and daily admissions)
│     * gold_patient_risk_features (Point-in-time feature store, one row per admission)
│     * gold_covid_outcomes (Pre-diagnosis features + 30-day COVID-19 outcomes, one row per patient)
```

---

## 7. Machine Learning Models & Transparency
All clinical models use point-in-time features, out-of-sample evaluation, and a simple baseline for comparison. Scores below are from the Synthea 10K run.

1. **COVID-19 Severe Outcome Risk** (`models/covid_outcome_model.joblib`) — primary clinical model
   * **Targets**: hospitalization, ICU admission, mechanical ventilation, and death within 30 days of COVID-19 diagnosis (8,820 diagnosed patients).
   * **Features**: only history recorded *before* the diagnosis date (age, 14 comorbidity flags, prior admissions, active medications, last BMI/BP/HbA1c/eGFR).
   * **Algorithm**: HistGradientBoostingClassifier per outcome; stratified 80/20 holdout + 5-fold CV.
   * **Results**: ROC-AUC 0.73 / 0.77 / 0.84 / 0.88 (hosp / ICU / vent / death), but an **age-only baseline already reaches 0.70 / 0.78 / 0.81 / 0.87**. In Synthea's COVID module age is the dominant driver, and the full model adds little beyond it.

2. **Unplanned 30-Day Readmission Classifier** (`models/readmission_model.joblib`)
   * **Label**: next admission 1–30 days after discharge, excluding transfers (<24h), in-hospital deaths and planned same-reason repeat stays (e.g. chemotherapy cycles). Only admissions with a full 30-day follow-up window are used.
   * **Split**: grouped by patient (no patient in both train and test).
   * **Results**: only ~120 unplanned readmissions (1.4%). Holdout ROC-AUC ≈ 0.80 (5-fold CV 0.78 ± 0.03) vs 0.68 for an age + LOS baseline; precision at the top decile is ~6%. Treat as indicative, not deployable.

3. **Length of Stay (LOS) Regressor** (`models/los_model.joblib`)
   * **Target**: observed inpatient days from admit/discharge timestamps; admission-time features only; patient-grouped split.
   * **Algorithm**: Gradient Boosting Regressor with absolute-error loss (stays are heavily skewed).
   * **Results**: MAE ≈ 1.1 days vs 2.8 days for a median-only baseline (R² ≈ 0.51).

4. **Pharmacy 30-Day Medication Demand Forecaster** (`models/pharmacy_demand_model.joblib`)
   * **Target**: Projected 30-day unit requirements.
   * **Algorithm**: Random Forest Regressor on historical burn and reorder thresholds.

5. **Laboratory Workload Forecaster** (`models/lab_workload_model.joblib`)
   * **Target**: Daily test investigation volume by clinical specialty.

6. **Hospital Bed & Resource Demand Forecaster** (`models/resource_demand_model.joblib`)
   * **Target**: Daily admission counts and emergency intake volume.

> ⚠️ Models 4–6 are operational heuristics that are still scored in-sample, and their targets are partly computed from their own inputs (e.g. demand = burn × 30). They have not yet been re-validated like models 1–3.

> ⚖️ **Model Transparency Disclaimer:** Every prediction displays confidence intervals, version tags, local contributing factors, and the mandatory warning: *"AI/ML decision support — not a medical diagnosis."*

---

## 8. Prescriptive Rules Architecture
MediNexus AI bridges prediction to action:
```
Prediction (ML Model) ➔ Business / Clinical Rule ➔ Prescriptive Recommendation ➔ Action Checklist
```
* **Clinical Prescriptions**: High readmission risk (>=70%) triggers the **Enhanced Transitional Care Protocol (TCP)**: Nurse 48-hour phone check-in, 7-day specialist consult, home telemetry for CHF, and bedside medication reconciliation.
* **Pharmacy Prescriptions**: Projected stock shortfall triggers automated calculation of safety buffer purchase orders and generates electronic PO dispatches.
* **Laboratory Prescriptions**: Workload utilization exceeding 85% triggers automated shifts in analyzer calibration schedules and evening bench staffing reassignments.
* **Hospital Surge Prescriptions**: Bed occupancy exceeding 90% activates **Level 4 Critical Surge Protocols**: expediting morning discharges and rescheduling non-urgent elective admissions.

---

## 9. Specialized AI Copilot Agents
MediNexus AI implements three specialized AI agents utilizing a tool-grounded architecture. Responses strictly isolate **FACTS**, **PREDICTIONS**, **RECOMMENDATIONS**, and **EVIDENCE**:

1. **MediCare Agent** (Attending Physician Role)
   * Grounded in Patient 360, longitudinal laboratory trajectories, and clinical guidelines.
   * Queries: Patient summaries, readmission explanations, and chronic disease protocols.
2. **HealthAnalyst Agent** (Hospital Administrator Role)
   * Grounded in operational KPIs, department revenues, and bed capacity models.
   * Queries: Readmission root-cause analysis ("Why did readmissions increase?"), occupancy projections, and hospital policies.
3. **PharmaLab Agent** (Pharmacist & Laboratory Roles)
   * Grounded in inventory stockout buffers, 30-day demand predictions, critical lab alarms, and equipment biosafety standards.

---

## 10. Grounded RAG Knowledge Base
Built-in synthetic institutional documents located in `documents/`:
* `hospital_policies/discharge_policy.txt` (POL-HOSP-001)
* `hospital_policies/appointment_policy.txt` (POL-HOSP-002)
* `hospital_policies/patient_privacy_policy.txt` (POL-HOSP-003)
* `clinical_guidelines/readmission_followup_guideline.txt` (CPG-CLIN-001)
* `pharmacy/medication_storage_policy.txt` (POL-PHARM-001)
* `pharmacy/inventory_policy.txt` (POL-PHARM-002)
* `laboratory/sample_handling_policy.txt` (POL-LAB-001)
* `laboratory/laboratory_safety_policy.txt` (POL-LAB-002)

* **Architecture**: Semantic text chunker ➔ TF-IDF vector embeddings with cosine similarity ➔ Grounded synthesis with citations. Works **100% locally offline**, with optional Google Gemini API support if `GEMINI_API_KEY` is provided.

---

## 11. Role-Based Access Control (RBAC) & Audit Trail
Seven preconfigured healthcare personas:
| Persona | User ID | Role | Accessible Layers | Primary Console |
| :--- | :--- | :--- | :--- | :--- |
| **Elena Rostova** | `data_engineer` | Lead Data & Analytics Engineer | Raw, Bronze, Silver, Gold | Data Engineering Console |
| **Dr. Sarah Chen, MD** | `dr_chen` | Attending Physician (Doctor) | Gold Clinical | Clinical Decision Support |
| **Rajesh Patel, PharmD**| `pharmacist_patel` | Chief Clinical Pharmacist | Gold Pharmacy | Pharmacy & Supply Chain |
| **Marcus Kim, MLS** | `lab_tech_kim` | Laboratory Operations Specialist | Gold Laboratory | Diagnostic Laboratory |
| **Claire Davis** | `receptionist_davis` | Outpatient Receptionist | Gold Appointments | Outpatient Reception Flow |
| **Arthur Holloway, MHA**| `admin_holloway` | Hospital Administrator | Gold Operations | Executive Dashboard |
| **Linus Sterling** | `it_admin_torvalds`| IT Security & Infrastructure Admin | Metadata & Gold Tables | Enterprise IT & Security |

* Default demo password for all accounts: `MediNexus@2026`
* **Enterprise Audit Log**: Every login, search query, patient access, model inference, and pipeline execution is logged in the DuckDB `audit_logs` table and written to `logs/audit.log`.

---

## 12. Quickstart & Installation

### Step 1: Clone and Enter Workspace
```powershell
cd "D:\Virtusa Project"
```

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Configure Optional Environment Variables
Copy `.env.example` to `.env` (optional, for Gemini API):
```powershell
cp .env.example .env
```
*(If left blank, MediNexus AI automatically runs using its high-fidelity deterministic local engine).*

---

## 13. Automated Execution Guide

### Step 1: Build Raw Source Tables from Synthea
With the Synthea CSVs in `data/synthea/csv/`, convert them into the 12 raw source tables:
```powershell
python src/ingestion/synthea_adapter.py
```

### Step 2: Run Full Medallion Lakehouse Pipeline
Execute Bronze Ingestion, Silver Cleansing, and Gold Dimensional Modeling in one command:
```powershell
python src/medallion/pipeline.py
```

### Step 3: Train Predictive Machine Learning Models
Train Readmission Risk, Length of Stay, Demand, and Workload models:
```powershell
python src/ml/train_demand.py
```

### Step 4: Run Automated Verification Tests
Verify all system layers, RBAC policies, and model predictions:
```powershell
python -m pytest
```

### Step 5: Launch the Streamlit Web Application
Start the interactive multi-role application:
```powershell
streamlit run app.py
```

Open your browser to `http://localhost:8501`.

---

## 14. Project Directory Structure
```
MediNexus_AI/
├── app.py                     # Main application entry point and RBAC router
├── requirements.txt           # Verified dependency versions
├── README.md                  # Comprehensive platform documentation
├── .env.example               # Environment variables template
├── .gitignore                 # Version control exclusions
│
├── config/
│   ├── constants.py           # Paths, catalogs (ICD-10, Labs, Meds), defaults
│   ├── roles.py               # RBAC policies and permission definitions
│   └── settings.py            # Environment settings and demo user directory
│
├── data/
│   ├── raw/                   # Multi-format raw files (CSV, JSON) with injected defects
│   ├── bronze/                # Raw Parquet files with ingestion metadata
│   ├── silver/                # Cleaned, standardized Parquet files
│   ├── gold/                  # 10 business-ready joined analytical Parquet models
│   ├── metadata/              # Generation summaries and execution runs
│   └── ml_results/            # Model performance artifacts
│
├── database/
│   └── healthcare.duckdb      # DuckDB analytical Lakehouse database
│
├── src/
│   ├── ingestion/             # Synthetic generation and Bronze ingestion
│   ├── medallion/             # Bronze, Silver, Gold, Quality, and Pipeline orchestrator
│   ├── analytics/             # Descriptive KPIs, Plotly figures, and Diagnostic drivers
│   ├── ml/                    # Feature matrices, model trainers, registry, and inference
│   ├── prescriptive/          # Clinical, Pharmacy, Laboratory, and Hospital rule engines
│   ├── rag/                   # Document loader, chunker, vector store, and grounded answers
│   ├── agents/                # Base agent, MediCare, HealthAnalyst, and PharmaLab agents
│   ├── security/              # Hashing, authentication, RBAC checks, and audit logging
│   └── utils/                 # DuckDB connectors, structured logging, and UI helpers
│
├── pages/
│   ├── welcome.py             # Landing page & architectural philosophy
│   ├── login.py               # Secure login with 1-click demo persona selector
│   ├── data_engineer.py       # Data Engineering console with 1-click pipeline
│   ├── doctor.py              # Clinical decision support & MediCare copilot
│   ├── pharmacist.py          # Inventory analytics, demand forecast & PharmaLab copilot
│   ├── laboratory.py          # Specimen throughput, critical alerts & PharmaLab copilot
│   ├── receptionist.py        # Outpatient appointment flow (Strictly privacy-redacted)
│   ├── administrator.py       # Executive hospital KPIs, diagnostics & HealthAnalyst copilot
│   └── it_admin.py            # Security audit stream & database table browser
│
├── models/                    # Serialized joblib models (readmission, los, demand)
├── documents/                 # Institutional guidelines and policy texts
├── tests/                     # Comprehensive pytest test suite
└── logs/                      # Application and enterprise security audit logs
```

---

## 15. Regulatory Notice & Healthcare Disclaimer
> **IMPORTANT NOTICE:** MediNexus AI is a demonstration decision-support intelligence platform utilizing synthetically generated healthcare data. It is developed strictly for research, educational, and workflow evaluation purposes. It does not provide medical diagnoses, treatment plans, or autonomous prescribing authority. All clinical decision-making must be performed by certified, licensed healthcare professionals.
#   M e d i N e x u s - A I 
 
 