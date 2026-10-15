"""
Hospital operations simulator for MediNexus AI.

Synthea simulates patients, not hospital operations. This module generates the operational
layer a hospital network runs on: staffing, outpatient demand vs. capacity, pharmacy dispensing,
and the equipment fleet. Every table is prefixed `sim_` and documented in
data/metadata/ops_simulation.json so simulated data is never mistaken for source records.

Design rules
- Anchored to the real data: the same 91 hospitals, sized in proportion to their real Synthea
  encounter volume; ventilator use follows the real Synthea ventilated-patient counts.
- Realistic structure: weekday pattern, winter seasonality, growth trend, public holidays,
  and multiplicative noise, so forecasts have signal to learn.
- Live replay: tables are generated through the end of the re-dated Synthea period and stored as
  `<table>_all`; `release_sim()` exposes only the days up to now as `<table>`, in step with
  the patient data (src/ingestion/redate_synthea.py).
- Never generates clinical outcomes (readmission, death, ICU); those come only from Synthea.

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
    "Internal Medicine": (0.30, 18),
    "Cardiology": (0.12, 14),
    "Pulmonology": (0.08, 14),
    "Oncology": (0.08, 12),
    "Orthopedics": (0.10, 16),
    "Neurology": (0.06, 13),
    "General Surgery": (0.10, 10),
    "Obstetrics & Gynecology": (0.08, 15),
    "Behavioral Health": (0.08, 11),
}
DRUG_CLASSES = {  # base share of dispensing, winter amplitude
    "Antihypertensive / Cardiovascular": (0.34, 0.02),
    "Antidiabetic": (0.17, 0.02),
    "Respiratory": (0.12, 0.35),
    "Statin": (0.08, 0.01),
    "Cardiac": (0.05, 0.05),
    "Anticoagulant / Antiplatelet": (0.05, 0.04),
    "Antibiotic": (0.05, 0.40),
    "Analgesic": (0.04, 0.06),
    "Antihistamine / Allergy": (0.03, -0.30),  # spring/summer peak
    "Oncology": (0.03, 0.00),
    "Critical Care / Anesthesia": (0.02, 0.08),
    "Hematologic": (0.02, 0.02),
}
EQUIPMENT = {  # per-bed density, min units, service interval (days), daily failure hazard, hours/day at 100%, typical load
    "CT scanner": (0.004, 1, 90, 0.0012, 20, 0.71),
    "MRI scanner": (0.003, 1, 90, 0.0015, 18, 0.80),
    "X-ray unit": (0.010, 2, 180, 0.0008, 16, 0.54),
    "Ventilator": (0.060, 4, 180, 0.0006, 24, None),
    "Infusion pump": (0.500, 20, 365, 0.0003, 24, 0.43),
    "Dialysis machine": (0.012, 1, 120, 0.0010, 14, 0.67),
    "Lab analyzer": (0.015, 2, 60, 0.0018, 22, 0.74),
}


DATED_TABLES = {"sim_outpatient_daily": "date", "sim_pharmacy_daily": "date", "sim_equipment_daily": "date", "sim_equipment_events": "date"}


def _simulation_end() -> pd.Timestamp:
    """End of the re-dated Synthea period when it exists (the live replay releases it day by day), else the data end."""
    meta = METADATA_DIR / "synthea_redate.json"
    if meta.exists():
        return pd.Timestamp(json.loads(meta.read_text(encoding="utf-8"))["redated_end"])
    return pd.Timestamp(query_df_strict("SELECT max(admission_date) AS d FROM gold_admissions").iloc[0]["d"])


def release_sim(as_of=None) -> Dict[str, int]:
    """Expose simulated days up to `as_of` (default: today) as the sim_ tables the platform reads."""
    from src.utils.database import execute_query, table_exists

    day = pd.Timestamp(as_of or datetime.now()).strftime("%Y-%m-%d")
    counts = {}
    for name, col in DATED_TABLES.items():
        if table_exists(f"{name}_all"):
            execute_query(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}_all WHERE CAST({col} AS DATE) <= CAST(? AS DATE)", [day])
            counts[name] = int(query_df_strict(f"SELECT count(*) AS n FROM {name}").iloc[0]["n"])
    return counts


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
    # Size hospitals 80–900 beds by their real relative encounter volume (log-scaled rank)
    v = np.log1p(hospitals["volume"].fillna(hospitals["volume"].median()))
    scaled = (v - v.min()) / max(1e-9, v.max() - v.min())
    hospitals["beds"] = np.round(80 + scaled * 820).astype(int)
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
    vent = query_df_strict("""
        SELECT hospital_id, CAST(admission_date AS DATE) AS d, COUNT(*) AS n
        FROM gold_admissions WHERE mechanical_ventilation = 1 GROUP BY 1, 2
    """)
    vent["d"] = pd.to_datetime(vent["d"])
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
                    "replacement_cost": round(float({"CT scanner": 1.2e6, "MRI scanner": 2.1e6, "X-ray unit": 1.5e5, "Ventilator": 3.5e4,
                                                     "Infusion pump": 3.0e3, "Dialysis machine": 3.0e4, "Lab analyzer": 2.5e5}[etype]
                                                    * rng.uniform(0.85, 1.15)), 2),
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
            if etype == "Ventilator":
                vh = vent[vent["hospital_id"] == h.hospital_id].set_index("d")["n"].reindex(days, fill_value=0).to_numpy()
                in_use = np.minimum(available, rng.binomial(n, 0.25, len(days)) + vh * 6)  # ~6 ventilator-days per ventilated stay
                util = in_use / np.maximum(available, 1)
            else:
                load = typical_load * rng.uniform(0.85, 1.15) * weekday_demand[dow] / weekday_demand.mean() * _seasonal(days, 0.05) * rng.lognormal(0, 0.06, len(days))
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
            # Dated tables are kept whole as <name>_all; release_sim() exposes the days up to now
            save_df_to_table(f"{name}_all" if name in DATED_TABLES else name, df, overwrite=True)
    if write_db:
        release_sim()

    counts = {name: int(len(df)) for name, df in tables.items()}
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    (METADATA_DIR / "ops_simulation.json").write_text(json.dumps({
        "generated_at": datetime.now().isoformat(), "seed": seed, "years": years,
        "date_range": [str(days[0].date()), str(days[-1].date())], "counts": counts,
        "simulated": True,
        "anchors": ["91 Synthea hospitals sized by real encounter volume", "ventilator use follows real Synthea ventilated stays"],
        "structure": ["weekday pattern", "winter seasonality", "growth trend", "holidays", "lognormal noise"],
        "never_generated": ["readmission", "mortality", "ICU", "any clinical outcome"],
    }, indent=2), encoding="utf-8")
    logger.info(f"Operations simulation complete: {counts}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(simulate(years=args.years, seed=args.seed))
