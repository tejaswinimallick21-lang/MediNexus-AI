# MediNexus AI — Repository Architecture

React + FastAPI platform over a DuckDB Medallion lakehouse. (The original Streamlit UI was retired; it remains in git history.)

```
MediNexus-AI-main/
├── package.json                ★ dev scripts: npm run backend | frontend | dev | seed | test
├── requirements.txt            Python dependencies
├── pytest.ini                  test discovery (tests/ + backend/tests/)
│
├── frontend/                   ★ React app (Vite + TypeScript) → http://localhost:5173
│   ├── vite.config.ts            dev server, proxy /api → :8000, Vitest config
│   └── src/
│       ├── main.tsx, App.tsx     entry + routes (one route per workspace)
│       ├── routes.ts             sidebar workspace list
│       ├── pages/                Login, Welcome, Reception (Patient Access), Laboratory, Pharmacy,
│       │                         Executive, Clinical Workstation, …
│       ├── components/           AppShell, AssistantDock (floating Nexa chat), ApprovalInbox, MemoryPanel,
│       │                         KPI cards, DataTable, Charts, state views,
│       │                         3D DnaHelix · NeuralGlobe · EcgTrace
│       ├── api/                  typed client (client.ts) + zod schemas per area
│       │   └── __fixtures__/     golden JSON written by backend tests; parsed by contract.test.ts
│       ├── hooks/                useApi, useAuth, useCursorPager
│       ├── lib/format.ts         USD, numbers, DD MMM YYYY dates
│       └── theme/tokens.css      design tokens
│
├── backend/                    ★ FastAPI → http://localhost:8000/api (OpenAPI docs at /docs)
│   ├── app/
│   │   ├── main.py               app factory: dev CORS, error handlers, routers
│   │   ├── core/                 config, security (bcrypt + JWT cookie), access (roles → pages),
│   │   │                         users (accounts in DuckDB, seeded once), deps (session + role checks), errors, pagination
│   │   ├── api/                  thin routers: auth, system, jobs, reception, operations, clinical, command,
│   │   │                         assistant (+ memory), data_platform, actions (approvals, sweep), security, knowledge, users
│   │   ├── agents/               Nexa agents: tools, engine (tool loop), providers (OpenAI/Claude/rules),
│   │   │                         actions (propose → approve → execute), sweep (07:00), learning, memory
│   │   ├── services/             business logic per workspace (SQL + model calls)
│   │   ├── schemas/              Pydantic request/response models
│   │   └── jobs/runner.py        background jobs with progress polling
│   ├── scripts/create_seed_users.py   writes gitignored seed_users.json (bcrypt hashes)
│   ├── seed_users.example.json   account template (no passwords)
│   └── tests/                    contract, access and parity tests
│
├── src/                        shared Python engine
│   ├── ingestion/                synthea_adapter.py, bronze loader, legacy Faker generator
│   ├── medallion/                silver (cleaning), gold (marts, labels, feature stores), pipeline
│   ├── ml/                       features, trainers, forecasting, evaluation, predict, registry
│   ├── analytics/                legacy KPI / diagnostic queries
│   ├── prescriptive/             care plan, procurement, lab staffing, bed-surge rules
│   ├── rag/                      policy loader, section chunker, hybrid BM25 + embeddings search, benchmark
│   ├── sandbox/                  isolated upload sandboxes (Data Engineering)
│   ├── security/                 audit log (+ legacy auth/rbac)
│   └── utils/database.py         DuckDB connection with lock retry
│
├── config/                     paths, settings, legacy personas
├── documents/                  hospital policies and clinical guidelines (RAG corpus)
├── scripts/                    bootstrap.py (rebuild everything), capture_screenshots.py
├── docs/                       setup, vision, architecture, screenshots
├── tests/                      pipeline, data and ML tests
│
└── not in git (generated / large)
    ├── data/synthea/csv/         Synthea export (16 CSVs)
    ├── data/raw → bronze → silver → gold/   Medallion layers (Parquet)
    ├── database/healthcare.duckdb   tables the API reads + registry, audit, purchase orders
    ├── models/*.joblib           trained models
    ├── backend/seed_users.json   login accounts (hashed)
    └── node_modules/
```

## Request flow
```
React page → api/*.ts (zod-validated) → Vite proxy /api → FastAPI router (role check)
  → services/*.py → DuckDB gold tables / models → Pydantic schema → JSON → UI states
```

## Data flow
```
Synthea CSV → synthea_adapter → data/raw → bronze → silver (clean) → gold (marts + labels)
  → model training (registry) → API services → React workspaces
```

## Data provenance (what is real, computed, simulated, estimated)
| Kind | Examples |
|---|---|
| Synthea records | admissions, stays, diagnoses, lab values, prescriptions, costs, deaths, ICU, hospitals |
| Computed by the pipeline | unplanned readmission flags, abnormal/critical lab flags, departments, KPIs, COVID outcomes |
| Simulated (labelled) | pharmacy stock levels, no-shows/cancellations, waiting times, payment status, blood group, phone numbers |
| Estimates (stated rule) | bed capacity & occupancy, lab bench capacity |
