# Streamlit → React + FastAPI Migration — Step 0: Inventory & Plan

Status: **awaiting approval** (no code changed yet).

---

## 1. Inventory

### 1.1 Repo facts
| Item | Finding |
|---|---|
| `AGENTS.md` | **Does not exist** in the repo (nor `CLAUDE.md`). |
| Git | **Not a git repository** (no `.git`). |
| Existing backend / API | **None.** Streamlit calls Python modules in-process. No FastAPI/Flask, no React, no `package.json`. |
| Tooling available | Node 24.14, npm 11.9, Python 3.12, FastAPI 0.142, Pydantic 2.12, uvicorn 0.54, PyJWT 2.8, bcrypt 3.2 (all already installed). |
| Gemini key loads | **False** (no `.env`; `config/settings.py` → `ENABLE_GEMINI=False`). Grok also False → "Deterministic Local Engine". |
| Kaggle CSVs | **None in the repo.** The Kaggle FHIR set was evaluated and rejected. The data source is the **Synthea COVID-19 10K CSV** (official Synthea GitHub mirror) in `data/synthea/csv/` — columns in §1.7. |
| Virtusa theme tokens | **None exist.** The only theme is the teal/slate palette in `app.py` CSS, `.streamlit/config.toml`, and `src/utils/helpers.PALETTE`. |
| Currency | All money is **USD** (Synthea = Massachusetts). `helpers.format_currency` renders `$1,234.56`. |

### 1.2 Current folder layout
```
MediNexus-AI-main/
├── app.py                  Streamlit entry: CSS, session init, sidebar nav, RBAC dispatcher
├── pages/                  9 Streamlit page modules (render_*_page functions)
├── config/                 constants.py, roles.py (7-role RBAC), settings.py (demo users, LLM keys)
├── src/
│   ├── ingestion/ medallion/   pipeline (Synthea adapter, bronze/silver/gold)
│   ├── ml/                     training, registry, predict.py
│   ├── analytics/              metrics.py (KPIs), descriptive.py (Plotly figs), diagnostic.py
│   ├── prescriptive/           clinical/hospital/laboratory/pharmacy rules
│   ├── agents/                 MediCare, HealthAnalyst, PharmaLab agents
│   ├── rag/                    TF-IDF knowledge base + benchmark
│   ├── security/               auth.py (bcrypt users), rbac.py, audit.py
│   └── utils/                  database.py (DuckDB), chat_ui.py (Streamlit chat widget), helpers.py
├── data/ database/healthcare.duckdb models/ documents/ logs/ tests/ (pytest)
```

### 1.3 Streamlit pages (title · inputs · outputs)
| File | Title | Inputs | Outputs |
|---|---|---|---|
| `app.py` (shell) | sidebar | nav buttons per allowed page; **role switcher selectbox (no password)**; Sign Out | active role card; readiness panel (Gold ready, ML registry, LLM provider, version) |
| `welcome.py` | MediNexus AI hero | 7 persona buttons + "Sign in" | static platform overview, persona cards |
| `login.py` | MediNexus Access Portal | 3 tabs: persona cards (username/password prefilled), custom credentials (+prefill select), **sign-up form** (name, username, email, role, dept, pwd×2) | session login, success/error messages |
| `doctor.py` | Clinical Workstation | worklist buttons, patient selectbox, free-text patient search, 5 tabs, care-plan checkboxes, chat input | 4 KPIs; high-risk worklist; risk-tier donut; Patient 360 card; COVID outcome cards; readmission + LOS cards; risk drivers; care protocol + checklist; lab trajectory chart; recent labs, active meds, admissions/diagnoses tables; MediCare chat |
| `administrator.py` | Hospital Executive Operations Console | chat input | 8 KPIs; admissions/readmission trend chart; department revenue chart; 4 forecast metrics; readmission drivers (insights + 2 tables); bed-surge capacity directive; HealthAnalyst chat |
| `pharmacist.py` | Pharmacy & Supply Chain Intelligence Console | medication selectbox; "Generate Electronic PO" button; chat input | 4 KPIs; stock vs reorder chart; stockout warnings table; demand forecast (4 metrics); procurement directives; PharmaLab chat |
| `laboratory.py` | Diagnostic Laboratory Operations Console | test-category selectbox; chat input | 4 KPIs; volume-by-category chart; critical value feed; capacity (3 metrics); staffing actions; PharmaLab chat |
| `receptionist.py` | Outpatient Reception & Care Flow Console | status filter; department filter | 4 KPIs; attendance donut; wait-time insights; appointment queue (25 rows) |
| `it_admin.py` | Enterprise IT & Security Audit Console | 4 tabs; audit role filter; audit action filter; table selectbox | 4 KPIs (DB size, tables, models, audit events); audit trail; table list + row count + 5-row preview; pipeline runs; ingestion runs |
| `data_engineer.py` (1,050 lines) | Data Engineering & Producer Console | file uploader + target-table select + "save" / "save & run"; legacy synthetic generator (scale radio + button); "Run pipeline (live)"; "View deployed state"; "Reset"; 6 tabs; RAG "Run benchmark"; benchmark suite filter | upload preview (rows/cols/nulls + table); live pipeline progress/logs; quality scorecard (4 metrics) + silver report; gold mart list + preview; model registry, 4 model metrics, confusion matrix, ROC, feature importance, LOS scatter, impact matrix, scorecard; RAG index stats + triad scorecard (10 metrics) + query telemetry; pipeline history; lineage diagram |

### 1.4 Where state lives today
- **`st.session_state` keys:** `authenticated`, `user`, `username`, `name`, `role`, `department`, `current_page` (routing), `selected_patient_id` (doctor), `pipeline_completed`, `pipeline_logs`, `trigger_pipeline_run`, `rag_benchmark_cache` (data engineer), `<agent>_history` per chatbot (`chat_ui.py`).
- **Cached functions:** none (`st.cache_*` is never used).
- **Module globals:** `src/security/auth._USER_STORE` (in-memory user dict, demo users re-hashed at import), `config/settings.DEMO_USERS` (plain demo passwords in source), `src/utils/database._DB_LOCK` (thread lock), RAG knowledge base singleton in `src/rag/knowledge_base.py`.
- Every page ends with an `if __name__ == "__main__":` block that fakes an authenticated session for standalone runs.

### 1.5 Business logic each page calls (to keep)
| Page | Functions |
|---|---|
| doctor | `metrics.compute_doctor_kpis`, `descriptive.get_risk_tier_donut_chart`, `descriptive.get_patient_lab_timeline`, `predict.predict_patient_covid_outcomes / _readmission / _los`, `clinical_rules.get_clinical_prescription_plan`, `MediCareAgent` |
| administrator | `compute_executive_kpis`, `get_admissions_trend_chart`, `get_department_revenue_chart`, `diagnostic.diagnose_readmissions`, `hospital_rules.get_hospital_capacity_plan`, `HealthAnalystAgent` |
| pharmacist | `compute_pharmacy_kpis`, `get_pharmacy_stock_chart`, `predict.predict_drug_demand`, `pharmacy_rules.get_pharmacy_prescriptive_actions`, `PharmaLabAgent` |
| laboratory | `compute_lab_kpis`, `get_lab_category_workload_chart`, `laboratory_rules.get_laboratory_prescriptive_plan`, `PharmaLabAgent` |
| receptionist | `compute_reception_kpis`, `get_appointment_status_chart`, `diagnostic.diagnose_waiting_times` |
| it_admin | `audit.get_audit_trail`, `model_registry.get_model_registry_summary` |
| data_engineer | `run_full_medallion_pipeline`, `get_pipeline_history`, `train_all_models`, `get_model_registry_summary`, `generate_healthcare_ecosystem`, RAG `knowledge_base` + `evaluation` benchmark |
| login / shell | `auth.authenticate_user`, `auth.register_user`, `rbac.check_page_access / get_allowed_pages`, `audit.log_audit_event` |

Note: `src/analytics/descriptive.py` returns **Plotly figures**, not data; these must be split into a data function (service) + a figure builder (Streamlit only).

### 1.6 Direct DB / model / filesystem access inside the Streamlit layer (moves to services)
- **Inline SQL via `query_df`:** doctor (worklist, selector, search, patient row, recent labs, meds, admissions/diagnoses), pharmacist (risk list, med list, med row), laboratory (critical feed, categories, category stats), receptionist (departments, filtered queue), administrator (row check), it_admin (counts, `information_schema` table list, `SELECT * FROM {selected_tbl}` with an f-string table name, pipeline & ingestion runs), data_engineer (last run, model count, quality report, gold previews via f-string, active registry).
- **Filesystem:** data_engineer writes uploaded files into `data/raw/` and **deletes** same-stem files (`unlink`); reads uploads with `pd.read_csv/read_parquet`; it_admin reads `DATABASE_PATH` size and `LOGS_DIR`.
- **Models:** only via `src/ml/predict.py` (`joblib` load through the registry) — no direct joblib in pages.
- **Auth weakness to fix:** the sidebar role switcher changes role **without a password**; demo plaintext passwords live in `config/settings.py`.

### 1.7 Data source CSVs (Synthea COVID-19 10K, `data/synthea/csv/`)
| File | Columns |
|---|---|
| allergies | START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION |
| careplans | Id, START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION, REASONCODE, REASONDESCRIPTION |
| conditions | START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION |
| devices | START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION, UDI |
| encounters | Id, START, STOP, PATIENT, ORGANIZATION, PROVIDER, PAYER, ENCOUNTERCLASS, CODE, DESCRIPTION, BASE_ENCOUNTER_COST, TOTAL_CLAIM_COST, PAYER_COVERAGE, REASONCODE, REASONDESCRIPTION |
| imaging_studies | Id, DATE, PATIENT, ENCOUNTER, BODYSITE_CODE, BODYSITE_DESCRIPTION, MODALITY_CODE, MODALITY_DESCRIPTION, SOP_CODE, SOP_DESCRIPTION |
| immunizations | DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, BASE_COST |
| medications | START, STOP, PATIENT, PAYER, ENCOUNTER, CODE, DESCRIPTION, BASE_COST, PAYER_COVERAGE, DISPENSES, TOTALCOST, REASONCODE, REASONDESCRIPTION |
| observations | DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, VALUE, UNITS, TYPE |
| organizations | Id, NAME, ADDRESS, CITY, STATE, ZIP, LAT, LON, PHONE, REVENUE, UTILIZATION |
| patients | Id, BIRTHDATE, DEATHDATE, SSN, DRIVERS, PASSPORT, PREFIX, FIRST, LAST, SUFFIX, MAIDEN, MARITAL, RACE, ETHNICITY, GENDER, BIRTHPLACE, ADDRESS, CITY, STATE, COUNTY, ZIP, LAT, LON, HEALTHCARE_EXPENSES, HEALTHCARE_COVERAGE |
| payer_transitions | PATIENT, START_YEAR, END_YEAR, PAYER, OWNERSHIP |
| payers | Id, NAME, ADDRESS, CITY, STATE_HEADQUARTERED, ZIP, PHONE, AMOUNT_COVERED, AMOUNT_UNCOVERED, REVENUE, COVERED_ENCOUNTERS, UNCOVERED_ENCOUNTERS, COVERED_MEDICATIONS, UNCOVERED_MEDICATIONS, COVERED_PROCEDURES, UNCOVERED_PROCEDURES, COVERED_IMMUNIZATIONS, UNCOVERED_IMMUNIZATIONS, UNIQUE_CUSTOMERS, QOLS_AVG, MEMBER_MONTHS |
| procedures | DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, BASE_COST, REASONCODE, REASONDESCRIPTION |
| providers | Id, ORGANIZATION, NAME, GENDER, SPECIALITY, ADDRESS, CITY, STATE, ZIP, LAT, LON, UTILIZATION |
| supplies | DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, QUANTITY |

---

## 2. Proposed folder layout
```
MediNexus-AI-main/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, CORS (dev only: http://localhost:5173), error handlers
│   │   ├── core/                config, security (bcrypt, JWT cookie), deps (current_user, require_roles), errors, pagination
│   │   ├── api/                 routers: auth, system, doctor, patients, executive, pharmacy, lab, reception, it, data, ml, jobs, agents
│   │   ├── services/            all page logic (SQL + calls into src/*); used by FastAPI AND Streamlit
│   │   ├── schemas/             Pydantic response/request models (no DataFrames cross the boundary)
│   │   └── jobs/                in-process job runner (thread pool) + job store for long tasks
│   ├── seed_users.example.json  committed template
│   ├── seed_users.json          .gitignored real seed (emails, bcrypt hashes, roles)
│   └── tests/                   unit tests per service + contract tests per endpoint
├── frontend/
│   ├── src/{pages,components,api,theme,hooks,lib}
│   ├── src/theme/tokens.css     design tokens
│   ├── vite.config.ts           proxy /api → http://localhost:8000
│   └── .env.example             VITE_API_BASE=/api
├── app.py + pages/              Streamlit, refactored to call backend/app/services (kept until retirement)
├── src/ config/ data/ …         unchanged (pipeline/ML out of scope)
├── docs/MIGRATION.md            per-page parity notes
└── Makefile                     make backend | make frontend | make dev (both)
```
Frontend language: **TypeScript** (typed API client + schemas parsed with `zod` in the client so Vitest can assert parsing).

## 3. API endpoints (one per page interaction)
All under `/api`. Errors: `{ "detail": str, "code": str }`. Lists >100 use `?limit=&cursor=` → `{ items: [...], next_cursor: str | null }`. Roles are re-checked on every endpoint.

### Shell, welcome, login
| Name | Method | Path | Request | Response |
|---|---|---|---|---|
| login | POST | `/auth/login` | `{email, password}` | `UserOut{email,name,role,persona,department,allowed_routes[]}` + httpOnly JWT cookie |
| logout | POST | `/auth/logout` | – | 204, cookie cleared |
| me | GET | `/auth/me` | – | `UserOut` |
| system status | GET | `/system/status` | – | `{gold_ready, ml_ready, llm_provider, version}` |
| platform overview | GET | `/platform/overview` (public) | – | `{app_name, tagline, personas[{key,title,description}]}` |

### Reception (`receptionist.py` → `/reception`)
| GET `/reception/kpis` | → `{total_appointments, completed, no_shows, cancelled, no_show_rate_pct, cancellation_rate_pct, avg_wait_minutes}` |
|---|---|
| GET `/reception/status-distribution` | → `[{status, count}]` |
| GET `/reception/wait-insights` | → `{question, summary, associated_factors[], by_hour[{hour, volume, avg_wait_min}]}` |
| GET `/reception/departments` | → `string[]` |
| GET `/reception/appointments?status=&department=&limit=&cursor=` | → `Page<AppointmentRow{appointment_id, patient_name, contact, date, time, doctor_name, department_name, status, waiting_time_minutes, reason_for_visit}>` |

### Laboratory (`laboratory.py` → `/laboratory`)
| GET `/lab/kpis` | → `{total_tests, abnormal_tests, critical_tests, abnormal_pct, critical_pct}` |
|---|---|
| GET `/lab/workload-by-category` | → `[{category, total, abnormal, critical}]` |
| GET `/lab/critical-alerts?limit=&cursor=` | → `Page<CriticalAlert{lab_id, patient_name, test_name, value, unit, reference_range, test_date, department}>` |
| GET `/lab/categories` | → `string[]` |
| GET `/lab/categories/{category}/capacity-plan` | → `{projected_daily_volume, utilization_pct, status, actions[]}` |

### Pharmacy (`pharmacist.py` → `/pharmacy`)
| GET `/pharmacy/kpis` | → `{total_items, high_risk_items, moderate_risk_items, total_dispensed_units, active_prescriptions}` |
|---|---|
| GET `/pharmacy/stock?limit=&cursor=` | → `Page<StockItem{medication_id, name, hospital, stock, reorder_level, days_of_supply, stockout_risk}>` |
| GET `/pharmacy/stockout-warnings?limit=` | → `StockItem[]` |
| GET `/pharmacy/medications` | → `[{medication_id, name}]` |
| GET `/pharmacy/medications/{id}/forecast` | → `{current_stock, predicted_30d_demand, projected_shortfall, suggested_order_units, plan{recommended_order_quantity, estimated_procurement_cost, actions[]}}` |
| POST `/pharmacy/purchase-orders` | `{medication_id, quantity}` → `{po_id, status, created_at}` (audited) |

### Executive (`administrator.py` → `/executive`)
| GET `/executive/kpis` | → 8 KPI fields |
|---|---|
| GET `/executive/admissions-trend` | → `[{month, admissions, readmissions}]` |
| GET `/executive/department-revenue` | → `[{department, revenue}]` |
| GET `/executive/forecasts` | → 4 forecast fields |
| GET `/executive/readmission-drivers` | → `diagnose_readmissions` typed |
| GET `/executive/capacity-plan` | → `{occupancy_pct, surge_level, directives[]}` |

### IT Security (`it_admin.py` → `/it`)
| GET `/it/overview` | → `{db_size_mb, table_count, active_models, audit_events}` |
|---|---|
| GET `/it/audit-events?role=&action=&limit=&cursor=` | → `Page<AuditEvent>` |
| GET `/it/tables` | → `[{name, type, row_count}]` |
| GET `/it/tables/{name}/preview?limit=5` | → `TablePreview{columns[{name,type}], rows[record]}` (name validated against `information_schema`, never interpolated raw) |
| GET `/it/pipeline-runs?limit=&cursor=` | → `Page<PipelineRun>` |
| GET `/it/ingestion-runs?limit=&cursor=` | → `Page<IngestionRun>` |

### Doctor (`doctor.py` → `/doctor`, `/doctor/patients/:id`)
| GET `/doctor/kpis` | → `{monitored_patients, high_risk, moderate_risk, active_admissions, readmission_rate}` |
|---|---|
| GET `/doctor/worklist?limit=` | → `PatientSummary[]` |
| GET `/doctor/risk-distribution` | → `[{tier, count}]` |
| GET `/patients?search=&limit=&cursor=` | → `Page<PatientSummary>` |
| GET `/patients/{id}` | → `Patient360` |
| GET `/patients/{id}/predictions` | → `{covid, readmission, los}` |
| GET `/patients/{id}/care-plan` | → `CarePlan{primary_recommendation, checklist[], rationale[]}` |
| GET `/patients/{id}/labs?limit=&cursor=` | → `Page<LabResult>` (also feeds the trajectory chart) |
| GET `/patients/{id}/medications` | → `Prescription[]` |
| GET `/patients/{id}/encounters` | → `[{admission…, diagnoses[]}]` |

### Agents (chat on doctor / executive / pharmacy / lab)
| POST `/agents/{medicare|healthanalyst|pharmalab}/chat` | `{message, patient_id?, history[]}` → `{facts[], predictions[], recommendations[], evidence[], notes}` (role-checked per agent; history kept client-side) |
|---|---|

### Data Engineering (`data_engineer.py` → `/data`)
| GET `/data/summary` | → last run counts, active models, quality index |
|---|---|
| GET `/data/quality-report` | → `QualityRow[]` |
| GET `/data/gold-tables` | → `[{name, description, row_count}]` (preview reuses `/it/tables/{name}/preview`) |
| GET `/data/pipeline-history?limit=&cursor=` | → `Page<PipelineRun>` |
| POST `/data/uploads` (multipart) | file + target table → `{staged_id, rows, columns, missing_values, preview}` |
| POST `/data/uploads/{staged_id}/commit` | → `{saved_path}` |
| GET `/ml/models` | → registry rows with parsed metrics |
| GET `/ml/models/{name}/evaluation` | → `{confusion_matrix, roc?, feature_importance[], baselines}` |
| GET `/rag/index-stats` | → `{documents, chunks, vocabulary, llm_engine}` |
| POST `/jobs/pipeline` | `{convert_synthea?: bool}` → `{job_id, status}` |
| POST `/jobs/train-models` | → `{job_id, status}` |
| POST `/jobs/rag-benchmark` | `{suite?}` → `{job_id, status}` |
| GET `/jobs/{job_id}` | → `{job_id, kind, status: queued|running|succeeded|failed, progress_pct, stage, logs[], result?, error?}` |

## 4. Page → route map
| Streamlit | React route | Roles (if 7 personas kept) |
|---|---|---|
| welcome | `/` | public |
| login | `/login` | public |
| receptionist | `/reception` | Receptionist |
| laboratory | `/laboratory` | Lab |
| pharmacist | `/pharmacy` | Pharmacist |
| administrator | `/executive` | Hospital Admin |
| it_admin | `/it` | IT Admin, Data Engineer |
| doctor | `/doctor`, `/doctor/patients/:id` | Doctor |
| data_engineer | `/data` | Data Engineer, IT Admin |

## 5. Migration order (one page per step)
0. **Foundation:** git baseline, backend skeleton (errors, CORS, pagination, jobs), auth (login/logout/me + seed file), `/system/status`, frontend scaffold (tokens, API client, app shell, skeletons, formatters), Makefile. Welcome + Login routes (needed to reach anything).
1. **Reception** — read-only, filters + pagination; proves the contract-test pattern.
2. **Laboratory** — selector-driven plan.
3. **Pharmacy** — first write (purchase order) + first chat agent.
4. **Executive** — charts + diagnostics.
5. **IT Security** — safe table preview, paginated audit log.
6. **Doctor** — largest page: patient search, 360, predictions, care plan, chat.
7. **Data Engineering** — jobs (pipeline, training, RAG benchmark), uploads.
8. Retirement commit "Retire Streamlit frontend" — **only on your go-ahead.**

Each step: move the page's inline logic into `backend/app/services/<page>.py` + unit tests → refactor the Streamlit page to call it → endpoints + schemas + pytest contract tests → React route + Vitest parsing tests → parity note in `docs/MIGRATION.md`.

## 6. Risks / assumptions to confirm
- **DuckDB single-writer lock.** Streamlit and FastAPI both open `database/healthcare.duckdb` read-write per query. Running both at once will intermittently fail with lock errors, and the 150 s pipeline job blocks everyone. Plan: read-only connections for reads + short retry/backoff in `database.py`; document "don't run the pipeline from both UIs at once".
- **Sign-up and the password-less role switcher are dropped** (spec auth = seeded users + login only). Switching persona = log out / log in.
- Demo plaintext passwords leave `config/settings.py`; seeds move to the `.gitignored` `backend/seed_users.json` (bcrypt hashes).
- Plotly stays in Streamlit only; React uses Recharts over the same service data.
- Legacy Faker generator button on Data Engineering is replaced by "Convert Synthea export" (Faker isn't installed).
- New installs needed: `python-multipart` (uploads); frontend npm deps (react, react-router, framer-motion, recharts, zod, vite, vitest, @testing-library). Packages come from PyPI / npm.
