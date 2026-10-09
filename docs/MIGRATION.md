# Streamlit → React + FastAPI Migration Log

Plan and inventory: [MIGRATION_PLAN.md](MIGRATION_PLAN.md). Decisions: 3 auth roles (admin / hcp / analyst) + persona; USD with US grouping; tokens from the existing teal/slate palette.

## Status
| Legacy Streamlit page | React route | Role | Status |
|---|---|---|---|
| shell + `welcome.py` + `login.py` | `/`, `/login` | all | ✅ |
| `receptionist.py` | `/reception` (Patient Access) | analyst | ✅ de-identified |
| `laboratory.py` | `/laboratory` | hcp | ✅ |
| `pharmacist.py` | `/pharmacy` | hcp | ✅ |
| `administrator.py` | `/executive` | analyst | ✅ |
| `it_admin.py` | `/it` | admin | ⏳ |
| `doctor.py` | `/doctor` | hcp | ⏳ |
| `data_engineer.py` | `/data` | admin | ⏳ |

Admins can open every workspace.

## How parity is tested
- **Backend contract:** `backend/tests/test_*.py` call each endpoint, validate the JSON against the endpoint's Pydantic model, and write the payload to `frontend/src/api/__fixtures__/<name>.json`.
- **Frontend contract:** `frontend/src/api/contract.test.ts` parses every fixture with the zod schema the UI uses (`fixtureSchemas.ts`); a fixture without a schema or a schema without a fixture fails.
- **Streamlit parity:** each page's numbers come from the same service functions; `backend/tests/test_parity_*.py` compares service output against the pre-migration calculations (`src/analytics/*`) for the same inputs.

---

## Foundation — shell, welcome, login
**Streamlit** shows: sidebar brand; active role card; console nav; sign out; readiness panel (Gold ready, ML registry, AI engine, version); welcome hero, pipeline flow, persona buttons; login form.
**React** shows the same via:
- `GET /api/system/status` → readiness panel (`get_system_status`, also used by `app.py`)
- `GET /api/platform/overview` → welcome hero, pipeline stages, persona cards
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` → session, role card, allowed consoles

Deliberate differences (both UIs): username login → **email** login against the seeded store; self sign-up and the password-less **role switcher removed** (security fix). Persona-to-console access is unchanged.

---

## Laboratory, Pharmacy, Executive
**Endpoints:** `/api/lab/*` (kpis, workload-by-category, daily-volume, categories, critical-alerts, capacity-plan), `/api/pharmacy/*` (kpis, stock, risk-by-category, stock/{id}/forecast, POST purchase-orders), `/api/executive/*` (kpis, admissions-trend, revenue-by-department, forecasts, readmission-drivers, capacity-plan), `POST /api/agents/{agent}/chat`.
**Parity:** lab KPIs match `compute_lab_kpis` exactly (pytest). Deliberate corrections vs Streamlit: removed hard-coded "STAT TAT 98.2%", "5 Facilities", "18 Adm/day", "99.6% ROC-AUC", "R² = 1.00"; projected admissions/lab volume/drug demand now come from forecasts with held-out scores and champion/challenger serving; lab bench capacity is an explicit estimate; purchase orders are persisted (`purchase_orders` table) and audited.
