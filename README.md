# MediNexus AI — Role-Based Healthcare Data-to-Decision Intelligence Platform

[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![Lakehouse](https://img.shields.io/badge/Lakehouse-Medallion%20(Bronze%2FSilver%2FGold)-teal)](https://duckdb.org/)
[![RBAC Security](https://img.shields.io/badge/Security-Strict%20RBAC%20%26%20Audit-red)](https://github.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Healthcare%20Demo-green)](https://github.com/)

---

> **New machine?** Follow [docs/SETUP.md](docs/SETUP.md): clone, add your keys to `.env`, download the Synthea export, then `python scripts/bootstrap.py` and `npm run dev`.

## 1. Project Overview
**MediNexus AI** is a role-aware clinical and operational decision intelligence platform. It ingests fragmented, heterogeneous healthcare data, runs it through an automated, quality-audited **Medallion Architecture (Bronze ➔ Silver ➔ Gold)**, trains predictive machine learning models, applies prescriptive clinical and operational rules, and serves role-tailored workspaces to three roles (admin, healthcare professional, analyst), with grounded AI agents that propose actions for human approval.

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
3. **Role-Aware Workspaces**: React workspaces per role with embedded predictive ML, prescriptive checklists and Nexa AI agents.

---

## 4. Platform Novelty
The novelty of MediNexus AI is **NOT** simply using React, DuckDB, or gradient boosting.

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
The platform runs on **Synthea** synthetic patient records (https://synthetichealth.github.io/synthea/downloads.html), **re-dated to the present day**: about 12,300 synthetic Massachusetts patients across 91 hospitals, with data running up to today. Synthea simulates full patient lifetimes from clinical disease models (cancers, diabetes, heart failure, COPD, kidney disease and more), so diagnoses, labs, medications, stays, costs and deaths are linked the way they are in real records.

**Re-dating and the live feed** (`src/ingestion/redate_synthea.py`). The source export is Synthea's COVID-19 10K set, which ends in May 2020 and is dominated by the COVID-19 module from 20 Jan 2020. We keep only records up to **31 Dec 2019** (so there is no COVID-19 period at all) and move every date, birth dates included, forward by the same whole number of weeks so the data ends about 30 days after the day it is anchored. Ages, weekdays and every patient's history stay consistent; nothing is invented. Records dated after "now" are held back and released each night by the **live data feed** (`backend/app/services/data_feed.py`, Data Engineering > Live data feed), which then rebuilds Bronze -> Silver -> Gold; when the held-back days run out, the source is re-anchored to the new date automatically.

`src/ingestion/synthea_adapter.py` maps the Synthea tables onto the 12 raw MediNexus source tables (SNOMED→ICD-10 crosswalk, LOINC reference ranges, encounter/claim cost roll-ups) and injects source-system defects for the Silver layer to repair.

* **Taken from Synthea:** demographics, deaths, admissions & timestamps, ICU stays, mechanical ventilation, diagnoses, labs/vitals, prescriptions, costs & payers, hospitals, clinicians (all dates shifted as above).
* **Simulated (Synthea has no equivalent):** blood group, phone numbers, room numbers, appointment wait times and missed visits (`is_simulated=1`), payment status, pharmacy stock levels (sized from real dispensing demand), and the `sim_` operations tables. Listed in `data/metadata/generation_summary.json` and `ops_simulation.json`.
* **Derived in Gold from event dates (never generated):** unplanned 30-day readmission and the 12-month outcome labels.
* **Lab/vital history is short:** this Synthea export records detailed results (blood pressure, HbA1c, eGFR…) almost only from mid-2019, i.e. roughly the last six months after re-dating. Older visits exist but carry few results, so many chronic patients have no monitoring test on record and show as open care gaps ("never recorded"). The count is what the data says; no readings are invented to lower it.
* **Bed capacity** is estimated as 1.25× each unit's observed peak census, so occupancy rates are relative, not reported capacity.

Setup: download `10k_synthea_covid19_csv.zip` (≈54 MB) and extract its CSVs into `data/synthea/csv/` (kept unmodified); `scripts/bootstrap.py` re-dates and releases it. A brand-new Synthea run (Java) with the same CSV schema can replace it at any time. The legacy Faker generator (`src/ingestion/generate_datasets.py`) is only used when no Synthea export is present.

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
│     * gold_outcome_risk (12-month outcome risk: training snapshot one year back + scoring snapshot today)
```

---

## 7. Machine Learning Models & Transparency
All clinical models use point-in-time features, out-of-sample evaluation, and a simple baseline for comparison. Scores below are from the re-dated Synthea run (records up to 2019, data ending October 2026).

1. **12-Month Outcome Risk** (`models/outcome_risk_model.joblib`, `src/ml/train_outcome.py`) — population-health model shown on Patient 360
   * **Targets**: any hospital admission within 12 months, and death within 12 months, for every living patient.
   * **Training**: a snapshot of all ~10,300 living patients one year before the end of the data (outcomes fully observed); features use only history before that date (age, 14 comorbidity flags, admissions in the past 5 years, active medications, last BMI/BP/HbA1c/eGFR). Scored on the same features as of today.
   * **Algorithm**: HistGradientBoostingClassifier per outcome; stratified 80/20 holdout + 5-fold CV.
   * **Results**: admission ROC-AUC **0.82** (CV 0.81) vs **0.65** age-only (309 admissions, 3.0%); death ROC-AUC **0.95** (CV 0.91) vs **0.87** age-only (72 deaths, 0.7%, so indicative).

2. **Unplanned 30-Day Readmission Classifier** (`models/readmission_model.joblib`)
   * **Label**: next admission 1–30 days after discharge, excluding transfers (<24h), in-hospital deaths and planned same-reason repeat stays (e.g. chemotherapy cycles). Only admissions with a full 30-day follow-up window are used.
   * **Split**: grouped by patient (no patient in both train and test).
   * **Results**: only 92 unplanned readmissions. Holdout ROC-AUC 0.78 (5-fold CV 0.79) vs 0.64 for an age + LOS baseline; only 25 readmissions in the test set. Treat as indicative, not deployable.

3. **Length of Stay (LOS) Regressor** (`models/los_model.joblib`)
   * **Target**: observed inpatient days from admit/discharge timestamps; admission-time features only; patient-grouped split.
   * **Algorithm**: Gradient Boosting Regressor with absolute-error loss.
   * **Results**: MAE 0.81 days vs 0.83 for a median-only baseline (R² ≈ 0). Pre-2020 stays are short and uniform, so the model adds essentially nothing over the median; shown as marginal.

4. **Pharmacy 30-Day Medication Demand Forecaster** (`models/pharmacy_demand_model.joblib`)
   * **Target**: units dispensed per hospital and medication over the next 30 days; test = the 3 most recent monthly forecast dates.
   * **Results**: gradient boosting MAE 0.39 vs 0.31 for "repeat the last 30 days", so **the baseline is served**: chronic prescriptions make next month repeat last month.

5. **Laboratory Workload Forecaster** (`models/lab_workload_model.joblib`) and 6. **Admission Demand Forecaster** (`models/resource_demand_model.joblib`)
   * **Target**: average daily lab tests per category / network admissions over the next 7 days; rolling-origin backtest, 6 folds of 60 days, each trained only on earlier data.
   * **Three methods compete; the most accurate is served**: gradient boosting, naive-7 (repeat the last week) and a **surge-aware average** (7/28-day blend while volume is stable, last week once volume shifts by more than ~35%).
   * **Results**: the surge-aware average is served for both: lab 5.6 vs 6.1 tests/day for naive-7 (8% better; gradient boosting 12.1), admissions 0.56 vs 0.61 per day (8% better; gradient boosting 0.69).

7–8. **Outpatient demand and drug-class demand** (simulated operations data): the gradient-boosting model is served, 41% and 62% more accurate than naive-7 in the same backtest.

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

## 9. Nexa AI Agents (agentic, human-approved)
Four role-scoped assistants share one engine (`backend/app/agents/`): **Nexa Care** (clinical), **Nexa Care · Lab & Pharmacy**, **Nexa Insight** (analyst) and **Nexa Ops** (admin, all workspaces).

* **Tool loop**: the LLM (OpenAI `gpt-4o-mini` or Claude) calls 23 typed tools over the same services the dashboards use; every number in an answer must come from a tool result, with its source cited. Without an API key a free rules engine answers from data only and never guesses.
* **Actions with approval**: `propose_*` tools create pending purchase orders, follow-ups and lab escalations in the **approval inbox**; nothing executes until a human approves. Everything is audited.
* **Morning sweep** (07:00 daily): free database checks find high-risk discharges without follow-up, stock-out risks and critical labs; AI-written justifications are capped.
* **Learning from approvals**: proposals show how similar ones were decided; kinds people keep rejecting are suppressed (never critical labs or zero-stock orders).
* **Memory**: short-term (last 3 turns) and explicit long-term memory ("remember …"), per user, visible and deletable, refusing any patient data.
* **Cost caps**: max 5 tool steps, 700-token replies, trimmed history and tool results.

---

## 10. Hybrid RAG Knowledge Base
21 synthetic hospital policies and clinical guidelines in `documents/` (plus admin uploads in Security & Infrastructure → Knowledge).

* **Architecture** (`src/rag/hybrid.py`): section-aware chunking ➔ BM25 keywords + embeddings (OpenAI `text-embedding-3-small`, cached; or free local LSA offline) ➔ query-adaptive score blend (keyword-heavy for policy codes like `POL-LAB-001`) ➔ abstains when nothing relevant matches. Answers cite `[Policy: <id> <section>]`.
* **Benchmark** (`src/rag/benchmark.py`, 56 questions: keyword, paraphrase, exact-code, out-of-scope) runs from the Security page.

---

## 11. Role-Based Access Control (RBAC) & Audit Trail
Sign-in is **email + password** (bcrypt) with a **JWT in an httpOnly cookie**. Every person has their own account with one of three roles (`backend/app/core/access.py`); admins oversee every workspace. The API re-checks the account and role on every request.

| Role | Starter account | Workspaces | Never sees |
| :--- | :--- | :--- | :--- |
| **Admin**: Platform Administrator | `admin@medinexus.org` | Every workspace, plus Data Engineering and Security & Infrastructure | — (full oversight) |
| **HCP**: Healthcare Professional | `hcp@medinexus.org` | Clinical Workstation, Pharmacy & Supply Chain, Laboratory Operations | Executive financials |
| **Analyst**: Operations Analyst | `analyst@medinexus.org` | Executive Operations, Patient Access | Patient names, contact details, diagnoses (pseudonymous IDs only) |

* **People management** (Security & Infrastructure → People): admins add a person with a role and department; the app issues a one-time temporary password, and the person must choose their own (10+ characters, a letter and a number) at first sign-in. Admins can change a role, disable or re-enable an account and reset a password. Disabling, resetting or changing a password signs that person out everywhere. Admins cannot change their own role or disable themselves, and the last administrator cannot be removed.
* Anyone can change their own password under **Your account** (click your name in the top bar).
* Accounts live in DuckDB (`app_users`). The three starter accounts come from the **.gitignored** `backend/seed_users.json`, created by `npm run seed` (demo password `MediNexus@2026`; pass `--password` for anything shared) and copied in on first start; seed changes never overwrite existing accounts. In development builds the sign-in page has a role dropdown that fills in the starter accounts; production builds omit it.
* Patient Access (former Receptionist console) is an analyst workspace: volumes, attendance, no-shows and waits with de-identified rows.
* **Enterprise Audit Log**: every login (and failed login), denied access, account change (create, role, disable, reset, password change; never a password), agent query, model inference and pipeline execution is logged in DuckDB `audit_logs` and `logs/audit.log`.

---

## 12. Quickstart
Full instructions for a new machine: **[docs/SETUP.md](docs/SETUP.md)**. In short:

```bash
pip install -r requirements.txt
npm install && npm --prefix frontend install
cp .env.example .env              # add OPENAI_API_KEY (optional) and MEDINEXUS_JWT_SECRET
# put the Synthea COVID-19 10K CSVs in data/synthea/csv/ (bootstrap re-dates them to today)
python scripts/bootstrap.py       # raw → Medallion → simulated ops → models → accounts
npm run dev                       # API http://localhost:8000 (docs /docs) + React http://localhost:5173
npm test                          # pytest (backend + pipeline) and Vitest (frontend contracts)
```

Optional environment: `MEDINEXUS_ENV=production` (disables the dev-only CORS origin), `MEDINEXUS_COOKIE_SECURE=true` behind HTTPS, `frontend/.env` → `VITE_API_BASE` (defaults to `/api`). All agent settings are listed in `.env.example`.

> DuckDB allows one writing process at a time; connections retry for up to 15 s on a lock. Tests run on a temporary copy of the database, so they can run while the app is up.

---

## 13. Project Directory Structure
See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the annotated tree, request flow and data provenance.

```
MediNexus-AI/
├── frontend/     React + Vite + TypeScript workspaces, Nexa chat dock, approval inbox
├── backend/      FastAPI: routers, services, schemas, Nexa agents, jobs, tests
├── src/          shared engine: ingestion, medallion, ml, analytics, prescriptive, rag, sandbox, security
├── config/       paths and settings
├── documents/    policy and guideline library (RAG corpus)
├── scripts/      bootstrap.py, capture_screenshots.py
├── docs/         setup, architecture, product vision, screenshots
└── tests/        pipeline, data quality, ML and RAG tests
```

---

## 14. Regulatory Notice & Healthcare Disclaimer
> **IMPORTANT NOTICE:** MediNexus AI is a demonstration decision-support intelligence platform utilizing synthetically generated healthcare data. It is developed strictly for research, educational, and workflow evaluation purposes. It does not provide medical diagnoses, treatment plans, or autonomous prescribing authority. All clinical decision-making must be performed by certified, licensed healthcare professionals.
