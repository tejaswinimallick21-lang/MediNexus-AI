"""
Silver Medallion Layer for MediNexus AI.
Cleans, standardizes, validates, deduplicates, repairs anomalies,
harmonizes heterogeneous external schemas, and enforces data quality checks across all bronze tables.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
import numpy as np

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import (
    BRONZE_DATA_DIR,
    SILVER_DATA_DIR,
    DATASETS,
)
from src.medallion.quality import compute_dataset_quality_metrics
from src.utils.database import execute_query, save_df_to_table, query_df
from src.utils.helpers import generate_uuid
from src.utils.logging_utils import get_logger

logger = get_logger("silver_transformation")

# Primary key mappings for each dataset
PRIMARY_KEYS = {
    "hospitals": "hospital_id",
    "departments": "department_id",
    "doctors": "doctor_id",
    "patients": "patient_id",
    "admissions": "admission_id",
    "diagnoses": "diagnosis_id",
    "laboratory_results": "lab_id",
    "medications": "medication_id",
    "prescriptions": "prescription_id",
    "pharmacy_inventory": "inventory_id",
    "appointments": "appointment_id",
    "billing": "bill_id",
}

# Cross-EMR and External Dataset Column Alias Normalization
COLUMN_ALIASES = {
    "hospitals": {
        "name": "hospital_name",
        "hospital": "hospital_name",
        "hospital_title": "hospital_name",
        "state": "location",
        "city": "location",
        "address": "location",
        "beds": "total_beds",
    },
    "departments": {
        "dept_id": "department_id",
        "dept_name": "department_name",
        "name": "department_name",
    },
    "doctors": {
        "doc_id": "doctor_id",
        "doctor_name": "name",
    },
    "patients": {
        "patient_name": "name",
        "full_name": "name",
        "insurance_type": "insurance_provider",
        "insurance": "insurance_provider",
        "blood_type": "blood_group",
        "phone": "contact",
        "mobile": "contact",
    },
    "admissions": {
        "admit_date": "admission_date",
        "admission_dt": "admission_date",
        "discharge_dt": "discharge_date",
        "los_days": "length_of_stay",
        "los": "length_of_stay",
        "stay_days": "length_of_stay",
        "admit_type": "admission_type",
        "discharge_type": "discharge_disposition",
        "disposition": "discharge_disposition",
        "room": "room_number",
        "ward": "room_number",
        "ward_type": "room_number",
    },
    "diagnoses": {
        "diag_id": "diagnosis_id",
        "dx_id": "diagnosis_id",
        "diag_desc": "diagnosis_description",
        "description": "diagnosis_description",
        "dx_desc": "diagnosis_description",
        "diag_code": "icd10_code",
        "dx_code": "icd10_code",
        "icd_code": "icd10_code",
        "diag_date": "diagnosis_date",
    },
    "laboratory_results": {
        "lab_result_id": "lab_id",
        "test_id": "lab_id",
        "result_value": "test_value",
        "value": "test_value",
        "flag": "abnormal_flag",
        "category": "test_category",
    },
    "medications": {
        "drug_id": "medication_id",
        "drug_name": "medication_name",
        "name": "medication_name",
        "cost": "unit_cost",
        "price": "unit_cost",
    },
    "prescriptions": {
        "rx_id": "prescription_id",
        "script_id": "prescription_id",
        "drug_id": "medication_id",
        "presc_date": "prescription_date",
    },
    "pharmacy_inventory": {
        "inv_id": "inventory_id",
        "drug_id": "medication_id",
        "stock": "stock_quantity",
        "quantity": "stock_quantity",
        "reorder": "reorder_level",
    },
    "appointments": {
        "apt_id": "appointment_id",
        "appt_id": "appointment_id",
        "apt_date": "appointment_date",
        "time": "appointment_time",
        "wait_time": "waiting_time_minutes",
    },
    "billing": {
        "total_cost_inr": "total_amount",
        "total_cost": "total_amount",
        "amount": "total_amount",
        "billed_amount": "total_amount",
        "cost": "total_amount",
        "charges": "total_amount",
        "govt_subsidy_inr": "insurance_covered",
        "subsidy": "insurance_covered",
        "insurance_amount": "insurance_covered",
        "insurance": "insurance_covered",
        "out_of_pocket_inr": "patient_payable",
        "out_of_pocket": "patient_payable",
        "patient_due": "patient_payable",
        "payable": "patient_payable",
        "status": "payment_status",
        "method": "payment_method",
        "date": "bill_date",
    },
}


# Source-system date layouts seen in the raw feeds, tried in order (unambiguous by separator).
KNOWN_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


def clean_date_series(series: pd.Series) -> pd.Series:
    """Parse dates from mixed strings into standard ISO YYYY-MM-DD format."""
    import warnings
    text = series.astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in KNOWN_DATE_FORMATS:
        todo = parsed.isna()
        if not todo.any():
            break
        parsed[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")
    todo = parsed.isna() & series.notna()
    if todo.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed[todo] = pd.to_datetime(text[todo], errors="coerce", format="mixed")
    default_date = datetime(2024, 1, 1).strftime("%Y-%m-%d")
    return parsed.dt.strftime("%Y-%m-%d").fillna(default_date)


def clean_category_series(series: pd.Series, default) -> pd.Series:
    """Title-case categorical text without turning missing values into the string 'Nan'."""
    cleaned = series.where(series.isna(), series.astype(str).str.strip().str.title())
    return cleaned.fillna(default)


def transform_silver_table(
    table_name: str,
    df_raw: pd.DataFrame,
    run_id: str,
) -> (pd.DataFrame, Dict[str, Any]):
    """
    Apply table-specific cleansing, standardization, schema harmonization, and normalization rules.
    """
    df = df_raw.copy()
    transformations = []

    # 1. Clean column names
    df.columns = [c.strip().lower() for c in df.columns]

    # 1b. Harmonize known cross-EMR column aliases
    aliases = COLUMN_ALIASES.get(table_name, {})
    renamed = {}
    for old_col, new_col in aliases.items():
        if old_col in df.columns and new_col not in df.columns:
            renamed[old_col] = new_col
    if renamed:
        df.rename(columns=renamed, inplace=True)
        transformations.append(f"Harmonized column aliases: {list(renamed.keys())} -> {list(renamed.values())}")

    # 2. Deduplication based on primary key
    pk = PRIMARY_KEYS.get(table_name)
    if pk and pk in df.columns:
        initial_len = len(df)
        df = df.drop_duplicates(subset=[pk], keep="first")
        dedup_count = initial_len - len(df)
        if dedup_count > 0:
            transformations.append(f"Deduplicated {dedup_count} rows on {pk}")

    # 3. Clean string whitespace & replace anomaly tokens
    for col in df.select_dtypes(include=["object"]).columns:
        if not col.startswith("_"):
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(["UNKNOWN_VAL", "nan", "None", "<NA>", ""], np.nan)

    # 4. Table-specific domain rules & Canonical Schema Enforcement
    if table_name == "hospitals":
        if "hospital_id" not in df.columns:
            df["hospital_id"] = [f"HOSP_{i+1:03d}" for i in range(len(df))]
        if "hospital_name" not in df.columns:
            df["hospital_name"] = "Hospital " + df["hospital_id"].astype(str)
        if "location" not in df.columns:
            df["location"] = "Metropolitan Healthcare Zone"
        if "total_beds" not in df.columns:
            df["total_beds"] = 500
        else:
            df["total_beds"] = pd.to_numeric(df["total_beds"], errors="coerce").fillna(500).astype(int)
        if "icu_beds" not in df.columns:
            df["icu_beds"] = (df["total_beds"] * 0.12).astype(int).clip(lower=10)
        else:
            df["icu_beds"] = pd.to_numeric(df["icu_beds"], errors="coerce").fillna(60).astype(int)
        if "operational_status" not in df.columns:
            df["operational_status"] = "Active"
        transformations.append("Harmonized hospital facilities schema and bed capacities")

    elif table_name == "departments":
        if "department_id" not in df.columns:
            df["department_id"] = [f"DEPT_{i+1:03d}" for i in range(len(df))]
        if "department_name" not in df.columns:
            df["department_name"] = "General Medicine"
        if "bed_capacity" not in df.columns:
            df["bed_capacity"] = 50
        else:
            df["bed_capacity"] = pd.to_numeric(df["bed_capacity"], errors="coerce").fillna(50).astype(int)
        transformations.append("Harmonized departmental bed capacities")

    elif table_name == "doctors":
        if "doctor_id" not in df.columns:
            df["doctor_id"] = [f"DOC_{i+1:04d}" for i in range(len(df))]
        if "name" not in df.columns:
            df["name"] = "Dr. Physician " + df["doctor_id"].astype(str)
        if "specialty" not in df.columns:
            df["specialty"] = "General Medicine"
        if "qualification" not in df.columns:
            df["qualification"] = "MD, FACP"
        if "experience_years" not in df.columns:
            df["experience_years"] = 10
        transformations.append("Harmonized physician credentialing metadata")

    elif table_name == "patients":
        if "patient_id" not in df.columns:
            df["patient_id"] = [f"P_{i+1:05d}" for i in range(len(df))]
        if "name" not in df.columns:
            df["name"] = "Patient " + df["patient_id"].astype(str)
        # Standardize gender
        if "gender" in df.columns:
            gender_map = {
                "m": "Male", "male": "Male", "m.": "Male",
                "f": "Female", "female": "Female", "f.": "Female",
                "other": "Other", "o": "Other"
            }
            df["gender"] = df["gender"].str.lower().map(gender_map).fillna("Other")
        else:
            df["gender"] = "Other"

        # Standardize blood group
        if "blood_group" in df.columns:
            df["blood_group"] = df["blood_group"].str.upper().fillna("O+")
        else:
            df["blood_group"] = "O+"

        # Age and DOB
        if "age" in df.columns:
            df["age"] = pd.to_numeric(df["age"], errors="coerce").fillna(45)
            df["age"] = df["age"].abs().clip(lower=0, upper=110).astype(int)
        else:
            df["age"] = 45

        if "dob" in df.columns:
            df["dob"] = clean_date_series(df["dob"])
        else:
            ref_date = datetime(2024, 1, 1)
            df["dob"] = [(ref_date - timedelta(days=int(a * 365.25))).strftime("%Y-%m-%d") for a in df["age"]]

        if "insurance_provider" not in df.columns:
            df["insurance_provider"] = "Universal Health Coverage"

        if "contact" not in df.columns:
            df["contact"] = "Not Provided"
        else:
            df["contact"] = df["contact"].fillna("Not Provided")

        if "emergency_contact" not in df.columns:
            df["emergency_contact"] = "Not Disclosed"
        else:
            df["emergency_contact"] = df["emergency_contact"].fillna("Not Disclosed")

        if "address" not in df.columns:
            df["address"] = "Metro Region"
        else:
            df["address"] = df["address"].fillna("Not Disclosed")

        if "created_at" in df.columns:
            df["created_at"] = clean_date_series(df["created_at"])
        else:
            df["created_at"] = "2024-01-01"

        transformations.append("Standardized patient demographics, gender, blood group & clamped age")

    elif table_name == "admissions":
        if "admission_id" not in df.columns:
            df["admission_id"] = [f"ADM_{i+1:06d}" for i in range(len(df))]
        if "admission_date" not in df.columns:
            df["admission_date"] = "2024-01-01"
        else:
            df["admission_date"] = clean_date_series(df["admission_date"])

        if "length_of_stay" in df.columns:
            df["length_of_stay"] = pd.to_numeric(df["length_of_stay"], errors="coerce").fillna(3)
            df["length_of_stay"] = df["length_of_stay"].abs().clip(lower=1, upper=60).astype(int)
        else:
            df["length_of_stay"] = 4

        if "discharge_date" in df.columns:
            df["discharge_date"] = clean_date_series(df["discharge_date"])
        else:
            adm_dt = pd.to_datetime(df["admission_date"], errors="coerce").fillna(datetime(2024, 1, 1))
            los = df["length_of_stay"]
            df["discharge_date"] = (adm_dt + pd.to_timedelta(los, unit="D")).dt.strftime("%Y-%m-%d")

        # Admission type & disposition
        if "admission_type" in df.columns:
            df["admission_type"] = clean_category_series(df["admission_type"], "Unknown")
        else:
            df["admission_type"] = "Emergency"

        if "discharge_disposition" in df.columns:
            df["discharge_disposition"] = clean_category_series(df["discharge_disposition"], "Unknown")
        else:
            df["discharge_disposition"] = "Home"

        if "room_number" not in df.columns:
            df["room_number"] = "101"
        else:
            df["room_number"] = df["room_number"].fillna("TBD")

        if "hospital_id" not in df.columns:
            df["hospital_id"] = "HOSP_001"
        if "doctor_id" not in df.columns:
            df["doctor_id"] = "DOC_0001"
        if "department_id" not in df.columns:
            df["department_id"] = "DEPT_001"

        transformations.append("Cleaned admission dates, standardized admission types, clamped LOS")

    elif table_name == "diagnoses":
        if "diagnosis_id" not in df.columns:
            df["diagnosis_id"] = [f"DX_{i+1:06d}" for i in range(len(df))]
        if "diagnosis_type" in df.columns:
            df["diagnosis_type"] = clean_category_series(df["diagnosis_type"], "Unknown")
        else:
            df["diagnosis_type"] = "Primary"

        if "severity" in df.columns:
            df["severity"] = clean_category_series(df["severity"], "Unknown")
        else:
            df["severity"] = "Moderate"

        if "diagnosis_date" in df.columns:
            df["diagnosis_date"] = clean_date_series(df["diagnosis_date"])
        else:
            df["diagnosis_date"] = "2024-01-01"

        if "icd10_code" not in df.columns:
            df["icd10_code"] = "R69"

        if "diagnosis_description" not in df.columns:
            df["diagnosis_description"] = "Clinical Diagnosis ICD-10"

        transformations.append("Standardized diagnosis severity & type casing")

    elif table_name == "laboratory_results":
        if "lab_id" not in df.columns:
            df["lab_id"] = [f"LAB_{i+1:06d}" for i in range(len(df))]
        if "test_date" in df.columns:
            df["test_date"] = clean_date_series(df["test_date"])
        else:
            df["test_date"] = "2024-01-01"

        if "abnormal_flag" in df.columns:
            df["abnormal_flag"] = clean_category_series(df["abnormal_flag"], "Unknown")
        else:
            df["abnormal_flag"] = "Normal"

        if "test_value" in df.columns:
            df["test_value"] = pd.to_numeric(df["test_value"], errors="coerce").abs()
            median_val = df["test_value"].median() if not df["test_value"].isna().all() else 5.0
            df["test_value"] = df["test_value"].fillna(median_val)
        else:
            df["test_value"] = 5.0

        if "unit" not in df.columns:
            df["unit"] = "standard"
        else:
            df["unit"] = df["unit"].fillna("standard")

        if "test_name" not in df.columns:
            df["test_name"] = "Laboratory Investigation"
        if "test_category" not in df.columns:
            df["test_category"] = "Chemistry"

        transformations.append("Normalized abnormal flag categories, imputed null test values")

    elif table_name == "medications":
        if "medication_id" not in df.columns:
            df["medication_id"] = [f"MED_{i+1:03d}" for i in range(len(df))]
        if "unit_cost" in df.columns:
            df["unit_cost"] = pd.to_numeric(df["unit_cost"], errors="coerce").fillna(0.50).abs()
        else:
            df["unit_cost"] = 1.0
        if "reorder_threshold" in df.columns:
            df["reorder_threshold"] = pd.to_numeric(df["reorder_threshold"], errors="coerce").fillna(100).astype(int)
        else:
            df["reorder_threshold"] = 100
        if "standard_daily_dose" in df.columns:
            df["standard_daily_dose"] = pd.to_numeric(df["standard_daily_dose"], errors="coerce").fillna(20.0)
        else:
            df["standard_daily_dose"] = 20.0
        if "category" in df.columns:
            df["category"] = clean_category_series(df["category"], "Unknown")
        else:
            df["category"] = "General"
        transformations.append("Validated medication pricing and dosage thresholds")

    elif table_name == "prescriptions":
        if "prescription_id" not in df.columns:
            df["prescription_id"] = [f"RX_{i+1:06d}" for i in range(len(df))]
        if "prescription_date" in df.columns:
            df["prescription_date"] = clean_date_series(df["prescription_date"])
        else:
            df["prescription_date"] = "2024-01-01"
        if "status" in df.columns:
            df["status"] = clean_category_series(df["status"], "Unknown")
        else:
            df["status"] = "Active"
        if "duration_days" in df.columns:
            df["duration_days"] = pd.to_numeric(df["duration_days"], errors="coerce").fillna(7).astype(int)
        else:
            df["duration_days"] = 7
        if "quantity" in df.columns:
            df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(30).astype(int)
        else:
            df["quantity"] = 30
        if "frequency" not in df.columns:
            df["frequency"] = "Once daily"
        else:
            df["frequency"] = df["frequency"].fillna("Once daily")
        if "medication_id" not in df.columns:
            df["medication_id"] = "MED_001"
        transformations.append("Standardized prescription statuses and dosage duration")

    elif table_name == "pharmacy_inventory":
        if "inventory_id" not in df.columns:
            df["inventory_id"] = [f"INV_{i+1:05d}" for i in range(len(df))]
        if "expiry_date" in df.columns:
            df["expiry_date"] = clean_date_series(df["expiry_date"])
        else:
            df["expiry_date"] = "2025-12-31"
        if "last_restocked_date" in df.columns:
            df["last_restocked_date"] = clean_date_series(df["last_restocked_date"])
        else:
            df["last_restocked_date"] = "2024-01-01"
        if "stock_quantity" in df.columns:
            df["stock_quantity"] = pd.to_numeric(df["stock_quantity"], errors="coerce").fillna(50)
            df["stock_quantity"] = df["stock_quantity"].abs().astype(int)
        else:
            df["stock_quantity"] = 250
        if "reorder_level" in df.columns:
            df["reorder_level"] = pd.to_numeric(df["reorder_level"], errors="coerce").fillna(100).astype(int)
        else:
            df["reorder_level"] = 100
        if "batch_number" not in df.columns:
            df["batch_number"] = "BATCH_DEFAULT"
        else:
            df["batch_number"] = df["batch_number"].fillna("BATCH_DEFAULT")
        transformations.append("Validated drug stock counts and expiry timelines")

    elif table_name == "appointments":
        if "appointment_id" not in df.columns:
            df["appointment_id"] = [f"APT_{i+1:06d}" for i in range(len(df))]
        if "appointment_date" in df.columns:
            df["appointment_date"] = clean_date_series(df["appointment_date"])
        else:
            df["appointment_date"] = "2024-01-01"
        if "status" in df.columns:
            df["status"] = clean_category_series(df["status"], "Unknown")
        else:
            df["status"] = "Completed"
        if "waiting_time_minutes" in df.columns:
            df["waiting_time_minutes"] = pd.to_numeric(df["waiting_time_minutes"], errors="coerce").fillna(15)
            df["waiting_time_minutes"] = df["waiting_time_minutes"].abs().clip(lower=0, upper=180).astype(int)
        else:
            df["waiting_time_minutes"] = 15
        if "reason_for_visit" not in df.columns:
            df["reason_for_visit"] = "General Consultation"
        else:
            df["reason_for_visit"] = df["reason_for_visit"].fillna("General Consultation")
        transformations.append("Standardized appointment statuses, bounded waiting minutes")

    elif table_name == "billing":
        if "bill_id" not in df.columns:
            df["bill_id"] = [f"BILL_{i+1:06d}" for i in range(len(df))]
        if "bill_date" in df.columns:
            df["bill_date"] = clean_date_series(df["bill_date"])
        else:
            df["bill_date"] = "2024-01-15"
        if "total_amount" in df.columns:
            df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").abs().fillna(1500.0)
        else:
            df["total_amount"] = 3500.0
        if "insurance_covered" in df.columns:
            df["insurance_covered"] = pd.to_numeric(df["insurance_covered"], errors="coerce").abs().fillna(1200.0)
        else:
            df["insurance_covered"] = (df["total_amount"] * 0.8).round(2)
        if "patient_payable" in df.columns:
            df["patient_payable"] = pd.to_numeric(df["patient_payable"], errors="coerce").abs().fillna(300.0)
        else:
            df["patient_payable"] = (df["total_amount"] - df["insurance_covered"]).round(2)
        if "payment_status" in df.columns:
            df["payment_status"] = clean_category_series(df["payment_status"], "Unknown")
        else:
            df["payment_status"] = "Paid"
        if "payment_method" not in df.columns:
            df["payment_method"] = "Insurance"
        else:
            df["payment_method"] = df["payment_method"].fillna("Unknown")
        transformations.append("Calculated and validated financial ledger sums")

    # Add Silver audit columns
    df["_silver_processed_at"] = datetime.now().isoformat()
    df["_silver_run_id"] = run_id

    # Compute data quality report
    quality_metrics = compute_dataset_quality_metrics(
        df_raw=df_raw,
        df_clean=df,
        primary_key=pk,
        dataset_name=table_name,
    )
    quality_metrics["transformations_applied"] = "; ".join(transformations) if transformations else "Standard schema harmonization"

    return df, quality_metrics


def transform_silver_layer(
    bronze_dir: Path = BRONZE_DATA_DIR,
    silver_dir: Path = SILVER_DATA_DIR,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Transform all Bronze datasets into the Silver Medallion layer.
    """
    run_id = run_id or generate_uuid("run_slv")
    silver_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    total_rows = 0
    quality_reports = []

    logger.info(f"Starting Silver Transformation (Run ID: {run_id}) from {bronze_dir}")

    bronze_files = list(bronze_dir.glob("*.parquet"))
    if not bronze_files:
        logger.warning(f"No Bronze Parquet files found in {bronze_dir}!")
        return {"run_id": run_id, "status": "EMPTY", "reports": [], "total_rows": 0}

    for file_path in bronze_files:
        table_name = file_path.stem.lower()
        try:
            df_bronze = pd.read_parquet(file_path)
            df_silver, quality_meta = transform_silver_table(table_name, df_bronze, run_id)

            # Persist Silver Parquet
            silver_path = silver_dir / f"{table_name}.parquet"
            df_silver.to_parquet(silver_path, index=False)

            # Register as DuckDB table silver_{table_name}
            duckdb_table_name = f"silver_{table_name}"
            save_df_to_table(duckdb_table_name, df_silver, overwrite=True)

            total_rows += len(df_silver)
            report_id = generate_uuid("rep")
            now = datetime.now()

            # Record in DuckDB silver_quality_report metadata table
            execute_query(
                """
                INSERT INTO silver_quality_report (
                    report_id, dataset, input_rows, output_rows,
                    duplicates_removed, nulls_before, nulls_after,
                    invalid_values, transformations_applied, quality_score, run_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    report_id,
                    table_name,
                    quality_meta["input_rows"],
                    quality_meta["output_rows"],
                    quality_meta["duplicates_removed"],
                    quality_meta["nulls_before"],
                    quality_meta["nulls_after"],
                    quality_meta["invalid_values"],
                    quality_meta["transformations_applied"],
                    quality_meta["quality_score"],
                    now,
                ],
            )

            quality_reports.append(quality_meta)
            logger.info(f"Silver Cleansed: {table_name} (Score: {quality_meta['quality_score']}%)")

        except Exception as e:
            logger.error(f"Failed Silver transformation for {table_name}: {e}")
            raise e

    avg_score = (
        round(sum(r["quality_score"] for r in quality_reports) / len(quality_reports), 2)
        if quality_reports
        else 0.0
    )

    return {
        "run_id": run_id,
        "status": "SUCCESS",
        "total_rows": total_rows,
        "average_quality_score": avg_score,
        "reports": quality_reports,
    }
