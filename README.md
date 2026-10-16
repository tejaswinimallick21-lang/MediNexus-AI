# MediNexus AI — Oncology Data-to-Decision Intelligence Platform

[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![Lakehouse](https://img.shields.io/badge/Lakehouse-Medallion%20(Bronze%2FSilver%2FGold)-teal)](https://duckdb.org/)
[![RBAC Security](https://img.shields.io/badge/Security-Strict%20RBAC%20%26%20Audit-red)](https://github.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Healthcare%20Demo-green)](https://github.com/)

---

> **New machine?** Follow [docs/SETUP.md](docs/SETUP.md): clone (the dataset comes with the repository), add your keys to `.env`, then `python scripts/bootstrap.py` and `npm run dev`.

## 1. Project Overview
**MediNexus AI** is a role-aware decision intelligence platform for a network of cancer centres. It ingests fragmented, heterogeneous healthcare data, runs it through an automated, quality-audited **Medallion Architecture (Bronze ➔ Silver ➔ Gold)**, trains predictive machine learning models, applies prescriptive clinical and operational rules, and serves role-tailored workspaces to three roles (admin, healthcare professional, analyst), with grounded AI agents that propose actions for human approval.

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
  * For the **Oncologist**: Ranks living patients by predicted 12-month mortality risk on a tumour-board worklist, explains the drivers, flags gaps in the oncology pathway (treatment not started within 30 days, a cycle without a blood count, a rising tumour marker) and proposes a care pathway.
  * For the **Pharmacist**: Tracks chemotherapy and supportive-care stock, forecasts 30-day demand and prepares purchase orders for approval.
  * For the **Laboratory Specialist**: Monitors test volumes including tumour markers, escalates critical values and forecasts bench workload.
  * For the **Oncology Analyst / Administrator**: Survival by cancer type and stage (Kaplan-Meier), time to treatment, cost of care and infusion/radiation capacity.
  * For the **Front desk**: Outpatient appointment flow and wait times, with clinical details redacted.

---

## 5. Data Source: synthetic oncology records (Synthea format)
The platform runs on **5,000 synthetic cancer patients** shipped with the repository as `data/synthea/oncology_5k.zip` (45 MB; its README describes every file). Every patient has one primary cancer (breast, prostate, lung, colon, melanoma, chronic lymphocytic leukaemia, non-Hodgkin lymphoma, pancreas) with a TNM stage I-IV, real chemotherapy regimens (AC-T, TCH, FOLFOX, FOLFIRINOX, R-CHOP, pembrolizumab, ...), surgery, radiation, tumour markers (PSA, CEA, CA 15-3, CA 19-9, S-100, LDH), labs, medicines, costs and deaths across 12 cancer centres. The files follow the Synthea CSV schema, so the same pipeline reads them.

**One fixed dataset** (`src/ingestion/oncology_dataset.py`): `prepare()` writes the cleaned data, as of **16 Oct 2026** (the day it was generated), to `data/synthea/current/`, which the pipeline reads. It repairs what the generator got wrong and records every repair in `data/metadata/oncology_dataset.json` (Data Engineering > Dataset shows them):
* 5,005 visits dated after the as-of date and 2,443 visits after the patient's death are removed, with everything recorded at them;
* 10,371 impossible lab values (negative counts, a percentage above 100) are dropped;
* end dates after the as-of date are cleared (still ongoing on that day). Nothing is invented or re-dated.

`src/ingestion/synthea_adapter.py` maps the CSVs onto the 12 raw MediNexus source tables (SNOMED→ICD-10 crosswalk with the cancer codes, tests matched by name because the source reuses some LOINC codes, drug catalogue by name because it reuses RxNorm codes, cancer type and stage per patient) and injects source-system defects for the Silver layer to repair.

* **Taken from the records:** demographics, deaths, cancer type, stage and diagnosis date, surgeries, chemotherapy / immunotherapy / targeted-therapy cycles, radiation sessions, diagnoses, labs and tumour markers, prescriptions, costs and payers, hospitals, clinicians.
* **Simulated (no equivalent in the records):** blood group, phone numbers, room numbers, appointment wait times and missed visits (`is_simulated=1`), payment status, pharmacy stock levels (sized from real dispensing demand), and the `sim_` operations tables (staffing, outpatient demand, drug-class dispensing, linear accelerators, PET-CT and infusion pumps). Listed in `data/metadata/generation_summary.json` and `ops_simulation.json`.
* **Derived in Gold from event dates (never generated):** treatment timeline, time to treatment, treatment status, survival and the 12-month mortality labels.

**Known limits of this synthetic data** (stated on the Dataset panel, not hidden):
* Every inpatient stay is one short surgical admission and nobody is admitted twice, so there are **no readmissions** and length of stay is not meaningful; the readmission and length-of-stay models are retired.
* Emergency visits occur only in the last weeks before death, so they are not used as model features (they would leak the outcome).
* Lab values do not respond to treatment (no white-cell dip after chemotherapy), so no toxicity model is trained.
* Medication costs and dispense counts are near-uniform across drugs, so costs are indicative.
* 362 diagnoses are dated 1-10 Sep 2026 (vs about 25 a month otherwise), which inflates the "awaiting treatment" count.

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
│     * gold_oncology_patients (Cancer type, stage, treatment pathway, tumour marker, survival per patient)
│     * gold_treatment_events (Every surgery, systemic-therapy cycle, radiation session and hospice start)
│     * gold_survival (Kaplan-Meier survival by cancer type and stage)
│     * gold_admissions (Surgical stays and billing sums)
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
All models use point-in-time features, out-of-sample evaluation and a simple baseline; the most accurate method is served (champion/challenger). Scores are from the oncology dataset as of 16 Oct 2026.

1. **12-Month Mortality Risk** (`models/outcome_risk_model.joblib`, `src/ml/train_outcome.py`): tumour-board worklist and Patient 360
   * **Target**: death within 12 months, for every living cancer patient.
   * **Training**: a snapshot one year before the end of the data (3,378 patients, 219 deaths, 6.5%); features use only history before that date: cancer type and stage, age, months since diagnosis, surgeries / chemotherapy / immunotherapy / radiation so far, tumour-marker status, haemoglobin, LDH, creatinine, BMI, comorbidities. Emergency and hospice visits are excluded (they leak the outcome in this data).
   * **Results**: gradient boosting ROC-AUC **0.88** (CV 0.88) vs **0.89** for a stage + cancer-type logistic regression and **0.63** for age alone. The model does **not** beat staging, so **the stage + type score is served** (top 10% of scores: 45% precision, 59% of deaths caught). The synthetic generator ties mortality to stage, so this is the honest result.

2. **Treatment demand forecaster** (`models/treatment_demand_model.joblib`): infusion-chair (chemo / immuno / targeted) and radiation sessions per day over the next 7 days; rolling-origin backtest, 6 folds of 60 days. The **surge-aware average** is served: MAE 0.55 vs 0.65 for naive-7 (15% better; gradient boosting 0.60).

3. **Laboratory workload forecaster** (`models/lab_workload_model.joblib`): tests per category over the next 7 days; gradient boosting is served, MAE 12.9 vs 17.6 for naive-7 (27% better).

4. **Pharmacy 30-day demand forecaster** (`models/pharmacy_demand_model.joblib`): units per hospital and medicine; gradient boosting MAE 7.5 vs 9.0 for "repeat the last 30 days" (17% better), served.

5-6. **Outpatient demand and drug-class demand** (simulated operations data): gradient boosting is served, 38% and 42% more accurate than naive-7.

**Survival analysis** (`gold_survival`, not ML): Kaplan-Meier survival from diagnosis by cancer type, stage and type × stage. 5-year survival: prostate 94%, breast 89%, melanoma 85%, colon 71%, lung 43%, pancreas 23%; stage I 94% → stage IV 31%.

**Retired:** unplanned readmission, length of stay and admission demand (the oncology data has no readmissions and one short surgical stay per patient).

> ⚖️ **Model Transparency Disclaimer:** Every prediction displays confidence intervals, version tags, local contributing factors, and the mandatory warning: *"AI/ML decision support — not a medical diagnosis."*

---

## 8. Prescriptive Rules Architecture
MediNexus AI bridges prediction to action:
```
Prediction (ML Model) ➔ Business / Clinical Rule ➔ Prescriptive Recommendation ➔ Action Checklist
```
* **Oncology Care Pathways** (`get_oncology_care_plan`): a top-band 12-month mortality risk triggers the **palliative and supportive care pathway** (palliative referral, tumour-board review, advance care plan); patients starting or in treatment get the **active treatment pathway** (blood count within 7 days before each cycle, antiemetic and growth-factor support, restaging); others follow the **survivorship pathway** (follow-up every 3-6 months, tumour marker and surveillance imaging).
* **Pharmacy Prescriptions**: Projected stock shortfall triggers automated calculation of safety buffer purchase orders and generates electronic PO dispatches.
* **Laboratory Prescriptions**: Workload utilization exceeding 85% triggers automated shifts in analyzer calibration schedules and evening bench staffing reassignments.

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
# the dataset (data/synthea/oncology_5k.zip) comes with the repository
python scripts/bootstrap.py       # raw → Medallion → simulated ops → models → accounts
npm run dev                       # API http://localhost:8000 (docs /docs) + React http://localhost:5173
npm test                          # pytest (backend + pipeline) and Vitest (frontend contracts)
```

Optional environment: `MEDINEXUS_ENV=production` (disables the dev-only CORS origin), `MEDINEXUS_COOKIE_SECURE=true` behind HTTPS, `frontend/.env` → `VITE_API_BASE` (defaults to `/api`). All agent settings are listed in `.env.example`.

**Deploying to a server:** `docs/DEPLOY_AZURE.md` sets it up on one Azure Linux VM (nginx + HTTPS + the API as a service) with the scripts in `deploy/`.

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
