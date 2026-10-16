"""
Hospital operations simulator for MediNexus AI.

Synthea simulates patients, not hospital operations. This module generates the operational
layer a hospital network runs on: staffing, outpatient demand vs. capacity, pharmacy dispensing,
and the equipment fleet. Every table is prefixed `sim_` and documented in
data/metadata/ops_simulation.json so simulated data is never mistaken for source records.

Design rules
- Anchored to the real data: the same oncology hospitals as the patient data, sized in proportion
  to their real encounter volume.
- Realistic structure: weekday pattern, winter seasonality, growth trend, public holidays,
  and multiplicative noise, so forecasts have signal to learn.
- Ends on the same day as the patient data (src/ingestion/oncology_dataset.py, AS_OF).
- Never generates clinical outcomes (death, response, toxicity); those come only from the patient data.

    python -m src.ingestion.ops_simulator --years 3 --seed 7
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import DATA_DIR, METADATA_DIR
from src.utils.database import query_df_strict, save_df_to_table
from src.utils.logging_utils import get_logger

logger = get_logger("ops_simulator")

OPS_DIR = DATA_DIR / "ops"

US_HOLIDAYS = {(1, 1), (7, 4), (12, 25), (11, 28), (5, 27), (9, 2)}  # approximate fixed dates
DEPARTMENTS = {  # share of physicians, outpatient visits per physician per day
    "Medical Oncology": (0.28, 14),
    "Radiation Oncology": (0.14, 22),
    "Surgical Oncology": (0.14, 10),
    "Hematology": (0.14, 14),
    "Radiology": (0.12, 28),
    "Primary Care": (0.18, 18),
}
DRUG_CLASSES = {  # base share of dispensing, winter amplitude
    "Chemotherapy": (0.28, 0.00),
    "Targeted / Immunotherapy": (0.12, 0.00),
    "Antiemetic": (0.16, 0.00),
    "Corticosteroid": (0.12, 0.02),
    "Growth Factor (G-CSF)": (0.08, 0.00),
    "Analgesic": (0.10, 0.03),
    "Antibiotic": (0.09, 0.35),  # infections peak in winter
    "Antidiarrheal": (0.05, 0.00),
}
EQUIPMENT = {  # per-bed density, min units, service interval (days), daily failure hazard, hours/day at 100%, typical load
    "Linear accelerator": (0.010, 1, 90, 0.0015, 14, 0.82),
    "PET-CT scanner": (0.004, 1, 90, 0.0014, 16, 0.76),
    "CT scanner": (0.006, 1, 90, 0.0012, 20, 0.71),
    "MRI scanner": (0.004, 1, 90, 0.0015, 18, 0.80),
    "Infusion pump": (0.800, 20, 365, 0.0003, 12, 0.62),
    "Lab analyzer": (0.015, 2, 60, 0.0018, 22, 0.74),
}
REPLACEMENT_COST = {"Linear accelerator": 3.0e6, "PET-CT scanner": 2.5e6, "CT scanner": 1.2e6, "MRI scanner": 2.1e6,
                    "Infusion pump": 3.0e3, "Lab analyzer": 2.5e5}


def _simulation_end() -> pd.Timestamp:
    """The day the patient data ends (the fixed oncology dataset), else the last admission."""
    meta = METADATA_DIR / "oncology_dataset.json"
    if meta.exists():
        return pd.Timestamp(json.loads(meta.read_text(encoding="utf-8"))["as_of"])
    return pd.Timestamp(query_df_strict("SELECT max(admission_date) AS d FROM gold_admissions").iloc[0]["d"])


def _seasonal(days: pd.DatetimeIndex, amplitude: float) -> np.ndarray:
    """Peak in mid-January for positive amplitude (negative amplitude peaks mid-July)."""
    return 1 + amplitude * np.cos(2 * np.pi * (days.dayofyear - 15) / 365.25)


def _holiday(days: pd.DatetimeIndex) -> np.ndarray:
    return np.array([0.35 if (d.month, d.day) in US_HOLIDAYS else 1.0 for d in days])


def simulate(years: int = 3, seed: int = 7, write_db: bool = True) -> Dict[str, int]:
    rng = np.random.default_rng(seed)
    end = _simulation_end()
    days = pd.date_range(end - pd.Timedelta(days=int(365.25 * years)) + pd.Timedelta(days=1), end, freq="D")
    years_since_start = (days - days[0]).days / 365.25
    dow = days.dayofweek.to_numpy()

    hospitals = query_df_strict("""
        SELECT hospital_id, hospital_name, TRY_CAST(encounter_volume AS DOUBLE) AS volume
        FROM silver_hospitals WHERE facility_type = 'Hospital' ORDER BY hospital_id
    """)
    # Size cancer centres 60–400 beds by their real relative encounter volume (log-scaled rank)
    v = np.log1p(hospitals["volume"].fillna(hospitals["volume"].median()))
    scaled = (v - v.min()) / max(1e-9, v.max() - v.min())
    hospitals["beds"] = np.round(60 + scaled * 340).astype(int)
    hospitals["physicians"] = np.maximum(12, np.round(hospitals["beds"] * rng.uniform(0.28, 0.40, len(hospitals)))).astype(int)
    hospitals["nurses"] = np.round(hospitals["beds"] * rng.uniform(1.0, 1.4, len(hospitals))).astype(int)

    # ---- staff roster ---------------------------------------------------------------------
    roster = []
    for h in hospitals.itertuples():
        for dept, (share, per_doc) in DEPARTMENTS.items():
            docs = max(1, int(round(h.physicians * share * rng.uniform(0.8, 1.2))))
            roster.append({
                "hospital_id": h.hospital_id, "hospital_name": h.hospital_name, "department_name": dept,
                "physicians": docs, "nurses": max(2, int(round(docs * rng.uniform(2.5, 4.0)))),
                "visits_per_physician_day": per_doc, "cost_per_physician_hour": round(float(rng.uniform(95, 160)), 2),
                "revenue_per_visit": round(float(rng.uniform(120, 260)), 2),
            })
    roster = pd.DataFrame(roster)

    # ---- outpatient demand vs capacity (hospital × day) -----------------------------------
    weekday_demand = np.array([1.18, 1.10, 1.05, 1.02, 0.98, 0.42, 0.25])
    weekday_staffing = np.array([0.97, 0.96, 0.95, 0.94, 0.93, 0.45, 0.26])
    holiday = _holiday(days)
    out_rows = []
    for h in hospitals.itertuples():
        hr = roster[roster["hospital_id"] == h.hospital_id]
        daily_capacity_full = float((hr["physicians"] * hr["visits_per_physician_day"]).sum())
        base_demand = daily_capacity_full * rng.uniform(0.78, 0.97)  # a few hospitals run hot
        growth = rng.uniform(0.01, 0.06)
        demand = (base_demand * weekday_demand[dow] * _seasonal(days, 0.10) * (1 + growth * years_since_start)
                  * holiday * rng.lognormal(0, 0.07, len(days)))
        absence = rng.beta(2, 30, len(days))  # sickness / leave
        capacity = daily_capacity_full * weekday_staffing[dow] * (1 - absence) * np.where(holiday < 1, 0.3, 1.0)
        demand, capacity = np.round(demand), np.round(capacity)
        backlog = np.zeros(len(days))
        served = np.zeros(len(days))
        carry = 0.0
        for i in range(len(days)):
            want = demand[i] + carry
            served[i] = min(want, capacity[i])
            carry = (want - served[i]) * 0.90  # 10% of the waiting list abandons each day
            backlog[i] = carry
        out_rows.append(pd.DataFrame({
            "date": days.strftime("%Y-%m-%d"), "hospital_id": h.hospital_id, "hospital_name": h.hospital_name,
            "demand": demand.astype(int), "capacity": capacity.astype(int), "served": served.astype(int),
            "backlog": np.round(backlog).astype(int),
            "avg_wait_days": np.round(np.where(served > 0, backlog / np.maximum(served, 1), 0), 2),
            "physicians_on_duty": np.round(hospitals.loc[hospitals["hospital_id"] == h.hospital_id, "physicians"].iloc[0]
                                           * weekday_staffing[dow] * (1 - absence)).astype(int),
        }))
    outpatient = pd.concat(out_rows, ignore_index=True)

    # ---- pharmacy dispensing (hospital × drug class × day) --------------------------------
    weekday_rx = np.array([1.12, 1.08, 1.04, 1.02, 1.00, 0.55, 0.40])
    rx_rows = []
    for h in hospitals.itertuples():
        site_units = h.beds * rng.uniform(5.5, 8.5)  # units/day across all classes
        for cls, (share, amp) in DRUG_CLASSES.items():
            units = (site_units * share * weekday_rx[dow] * _seasonal(days, amp) * (1 + 0.03 * years_since_start)
                     * holiday * rng.lognormal(0, 0.12, len(days)))
            rx_rows.append(pd.DataFrame({
                "date": days.strftime("%Y-%m-%d"), "hospital_id": h.hospital_id, "drug_class": cls,
                "units_dispensed": rng.poisson(np.maximum(units, 0.1)),
            }))
    pharmacy = pd.concat(rx_rows, ignore_index=True)

    # ---- equipment fleet, daily utilization and events ------------------------------------
    assets, eq_daily, events = [], [], []
    for h in hospitals.itertuples():
        for etype, (density, minimum, interval, hazard, hours, typical_load) in EQUIPMENT.items():
            n = max(minimum, int(round(h.beds * density)))
            age_years = rng.gamma(2.2, 2.4, n)
            last_service = end - pd.to_timedelta(rng.integers(0, int(interval * 1.6), n), unit="D")
            ids = [f"EQ_{h.hospital_id[-4:]}_{etype.split()[0][:3].upper()}_{i + 1:03d}" for i in range(n)]
            for i in range(n):
                assets.append({
                    "asset_id": ids[i], "hospital_id": h.hospital_id, "hospital_name": h.hospital_name, "equipment_type": etype,
                    "install_date": (end - pd.Timedelta(days=int(age_years[i] * 365))).strftime("%Y-%m-%d"),
                    "age_years": round(float(age_years[i]), 1), "service_interval_days": interval,
                    "last_service_date": last_service[i].strftime("%Y-%m-%d"),
                    "next_service_due": (last_service[i] + pd.Timedelta(days=interval)).strftime("%Y-%m-%d"),
                    "replacement_cost": round(float(REPLACEMENT_COST[etype] * rng.uniform(0.85, 1.15)), 2),
                })
            # Daily failures: hazard rises with age and overdue service; each failure takes units down for days
            ages = age_years.mean()
            overdue = float(((end - last_service).days > interval).mean())
            daily_hazard = hazard * (1 + 0.15 * ages) * (1 + overdue)
            failures = rng.poisson(daily_hazard * n, len(days))
            down_days = np.zeros(len(days))
            for i in np.nonzero(failures)[0]:
                repair = int(rng.integers(1, 6))
                down_days[i: i + repair] += failures[i]
                events.append({"date": days[i].strftime("%Y-%m-%d"), "hospital_id": h.hospital_id, "equipment_type": etype,
                               "event": "failure", "units": int(failures[i]), "repair_days": repair})
            available = np.clip(n - down_days, 0, n)
            load = (typical_load * rng.uniform(0.85, 1.15) * weekday_demand[dow] / weekday_demand.mean()
                    * _seasonal(days, 0.05) * rng.lognormal(0, 0.06, len(days)))
            util = np.clip(load, 0, 1)
            eq_daily.append(pd.DataFrame({
                "date": days.strftime("%Y-%m-%d"), "hospital_id": h.hospital_id, "equipment_type": etype, "units": n,
                "units_available": available.astype(int), "utilization_pct": np.round(util * 100, 1),
                "hours_used": np.round(util * available * hours, 1),
            }))
    assets, eq_daily, events = pd.DataFrame(assets), pd.concat(eq_daily, ignore_index=True), pd.DataFrame(events)

    tables = {
        "sim_hospital_profile": hospitals[["hospital_id", "hospital_name", "beds", "physicians", "nurses"]],
        "sim_staff_roster": roster,
        "sim_outpatient_daily": outpatient,
        "sim_pharmacy_daily": pharmacy,
        "sim_equipment_assets": assets,
        "sim_equipment_daily": eq_daily,
        "sim_equipment_events": events,
    }
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(OPS_DIR / f"{name}.parquet", index=False)
        if write_db:
            save_df_to_table(name, df, overwrite=True)
    if write_db:  # full copies kept by the earlier day-by-day release, no longer used
        from src.utils.database import execute_query

        for name in ("sim_outpatient_daily", "sim_pharmacy_daily", "sim_equipment_daily", "sim_equipment_events"):
            execute_query(f"DROP TABLE IF EXISTS {name}_all")

    counts = {name: int(len(df)) for name, df in tables.items()}
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    (METADATA_DIR / "ops_simulation.json").write_text(json.dumps({
        "generated_at": datetime.now().isoformat(), "seed": seed, "years": years,
        "date_range": [str(days[0].date()), str(days[-1].date())], "counts": counts,
        "simulated": True,
        "anchors": [f"{len(hospitals)} oncology hospitals sized by real encounter volume"],
        "structure": ["weekday pattern", "winter seasonality", "growth trend", "holidays", "lognormal noise"],
        "never_generated": ["mortality", "treatment response", "toxicity", "any clinical outcome"],
    }, indent=2), encoding="utf-8")
    logger.info(f"Operations simulation complete: {counts}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(simulate(years=args.years, seed=args.seed))
