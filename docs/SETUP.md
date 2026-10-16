# Setting up MediNexus AI on a new machine

Git carries the code, the policy library and the docs. It does **not** carry the data (≈900 MB),
the DuckDB database (≈200 MB), the trained models, the sign-in accounts or your API keys — these are
rebuilt locally in about 15–30 minutes.

## 1. Prerequisites

- Python 3.12 (Anaconda works) and Node.js 20+
- Git

## 2. Get the code

```bash
git clone https://github.com/<your-account>/<your-repo>.git
cd <your-repo>
pip install -r requirements.txt
npm install
npm --prefix frontend install
```

## 3. The dataset

Nothing to download: the oncology dataset (5,000 synthetic cancer patients in the Synthea CSV format)
comes with the repository as `data/synthea/oncology_5k.zip` (45 MB). The bootstrap script cleans it and
fixes it as of its as-of date (16 Oct 2026) into `data/synthea/current/`; see README section 5.

## 4. Add your keys (never committed)

Copy `.env.example` to `.env` and fill in:

- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) for the AI assistants — optional; without it they use the free rules engine
- `MEDINEXUS_JWT_SECRET` — any long random string
- `MEDINEXUS_SEED_PASSWORD` — the password for the three starter accounts (leave empty for the demo password)

The bootstrap script creates `.env` from the example if it is missing.

## 5. Rebuild data, database, models and accounts

```bash
python scripts/bootstrap.py
```

It runs, in order, skipping anything already done:

| Step | Command |
|---|---|
| Prepare the oncology dataset (clean, fix as of its date) | `python -m src.ingestion.oncology_dataset` |
| Synthea-format CSVs → raw tables | `python -m src.ingestion.synthea_adapter` |
| Medallion pipeline (Bronze → Silver → Gold) | `python -m src.medallion.pipeline` |
| Simulated operations data | `python -m src.ingestion.ops_simulator --years 3 --seed 7` |
| Train the ML models | `python -m src.ml.train_demand` |
| Sign-in accounts | `python -m backend.scripts.create_seed_users` |

The simulator and model training use fixed seeds, so the numbers match the original machine closely.

## 6. Run

```bash
npm run dev
```

Open http://localhost:5173 and sign in (admin / hcp / analyst starter accounts are in the login page's role picker in development).
Then add real people as admin under Security & Infrastructure → People: each gets a temporary password and chooses their own at first sign-in.

## What is real and what is simulated

| Source | Used for |
|---|---|
| **Oncology dataset** (synthetic cancer patients, Synthea format) | Patients, cancer type and stage, diagnoses, surgery, chemotherapy / immunotherapy / radiation, labs and tumour markers, prescriptions, billing, completed visits, deaths |
| **Simulated by this project** (labelled in the UI) | Staffing, outpatient demand vs capacity, pharmacy dispensing by drug class, equipment, missed appointments, waiting times, some stock fields |
| **Demo documents** | The policy and guideline library under `documents/` (synthetic, not medical advice) |

No outcome labels (mortality, treatment response) are ever simulated.
