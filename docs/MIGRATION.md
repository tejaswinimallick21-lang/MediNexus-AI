# Streamlit → React + FastAPI Migration Log

Plan and inventory: [MIGRATION_PLAN.md](MIGRATION_PLAN.md). Decisions: 3 auth roles (admin / hcp / analyst) + persona; USD with US grouping; tokens from the existing teal/slate palette.

## Status
| Streamlit page | React route | Status |
|---|---|---|
| shell (`app.py` sidebar) + `welcome.py` + `login.py` | `/`, `/login`, app shell | ✅ Foundation |
| `receptionist.py` | `/reception` | ⏳ |
| `laboratory.py` | `/laboratory` | ⏳ |
| `pharmacist.py` | `/pharmacy` | ⏳ |
| `administrator.py` | `/executive` | ⏳ |
| `it_admin.py` | `/it` | ⏳ |
| `doctor.py` | `/doctor` | ⏳ |
| `data_engineer.py` | `/data` | ⏳ |

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
