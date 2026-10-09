"""
High-Performance Synthetic Healthcare Dataset Generator for MediNexus AI.
Generates 12 interconnected datasets with 50,000+ rows per core dataset,
maintaining realistic clinical correlations and intentional data quality defects.
"""

import sys
import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from faker import Faker

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import (
    RAW_DATA_DIR,
    METADATA_DIR,
    DEFAULT_COUNTS,
    BLOOD_GROUPS,
    GENDERS,
    ADMISSION_TYPES,
    DISCHARGE_DISPOSITIONS,
    PAYMENT_STATUSES,
    APPOINTMENT_STATUSES,
    ICD10_CATALOG,
    LAB_CATALOG,
    MEDICATION_CATALOG,
    HOSPITAL_DEPARTMENTS,
)
from src.ingestion.ingestion_utils import inject_realistic_imperfections


def generate_healthcare_ecosystem(
    counts: dict = None,
    seed: int = 42,
    output_dir: Path = RAW_DATA_DIR,
) -> dict:
    """
    Generate 12 interconnected healthcare datasets with 50,000+ rows per core dataset.
    Optimized for high-performance vectorized generation.
    """
    counts = counts or DEFAULT_COUNTS
    random.seed(seed)
    np.random.seed(seed)
    fake = Faker("en_US")
    Faker.seed(seed)

    output_dir.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic healthcare ecosystem (Seed: {seed}, Enterprise Scale 50k+)...")

    # 1. Hospitals (10 records)
    num_hospitals = counts.get("hospitals", 10)
    hospital_names = [
        "Metropolitan General Hospital", "Saint Jude Health Pavilion",
        "Apex Memorial Medical Center", "Riverside University Hospital",
        "Beacon Hill Community Hospital", "Central City Presbyterian",
        "Northwestern Memorial Clinic", "Mercy Hospital of Diagnostics",
        "Valley Crest Medical Center", "Harborview Clinical Institute"
    ]
    hospitals = []
    for i in range(num_hospitals):
        h_id = f"HOSP_{i+1:03d}"
        hospitals.append({
            "hospital_id": h_id,
            "hospital_name": hospital_names[i % len(hospital_names)],
            "location": f"Zone {i+1}, Metropolitan Healthcare District",
            "total_beds": random.choice([350, 500, 650, 800, 1000]),
            "icu_beds": random.choice([40, 60, 90, 120, 80]),
            "operational_status": "Active",
        })
    df_hospitals = pd.DataFrame(hospitals)

    # 2. Departments (25 records)
    departments = []
    dept_id_counter = 1
    for h in hospitals:
        for d_name in HOSPITAL_DEPARTMENTS[:3]:  # Top 3 depts per hospital
            departments.append({
                "department_id": f"DEPT_{dept_id_counter:03d}",
                "hospital_id": h["hospital_id"],
                "department_name": d_name,
                "bed_capacity": random.randint(35, 120),
            })
            dept_id_counter += 1
    df_departments = pd.DataFrame(departments)

    # 3. Doctors (500 records)
    num_doctors = counts.get("doctors", 500)
    specialties = [
        "Cardiology", "Internal Medicine", "Pulmonology", "Emergency Medicine",
        "General Surgery", "Oncology", "Endocrinology", "Nephrology"
    ]
    doctor_names_pool = [fake.first_name() + " " + fake.last_name() for _ in range(200)]
    dept_ids_pool = df_departments["department_id"].tolist()
    dept_to_hosp = dict(zip(df_departments["department_id"], df_departments["hospital_id"]))

    doctors = []
    for i in range(num_doctors):
        d_dept = np.random.choice(dept_ids_pool)
        doctors.append({
            "doctor_id": f"DOC_{i+1:04d}",
            "hospital_id": dept_to_hosp[d_dept],
            "department_id": d_dept,
            "name": f"Dr. {np.random.choice(doctor_names_pool)}, MD",
            "specialty": np.random.choice(specialties),
            "qualification": np.random.choice(["MD, FACC", "MD, FACP", "MD, FCCP", "MBBS, MD"]),
            "experience_years": int(np.random.randint(3, 35)),
            "contact": f"+1-555-DOC-{i+1:04d}",
        })
    df_doctors = pd.DataFrame(doctors)
    doctor_ids = [d["doctor_id"] for d in doctors]
    doc_lookup = {d["doctor_id"]: (d["hospital_id"], d["department_id"]) for d in doctors}

    # 4. Patients (50,000+ records)
    num_patients = counts.get("patients", 50000)
    print(f"Generating {num_patients:,} Patient records...")
    
    # Pre-generate high-performance pools
    pool_size = min(1500, num_patients)
    first_names_m = [fake.first_name_male() for _ in range(pool_size // 2)]
    first_names_f = [fake.first_name_female() for _ in range(pool_size // 2)]
    last_names = [fake.last_name() for _ in range(pool_size)]
    streets = [f"{np.random.randint(100, 9999)} Health Ave, Suite {np.random.randint(10, 99)}" for _ in range(pool_size)]
    phones = [f"+1-555-{np.random.randint(100, 999):03d}-{np.random.randint(1000, 9999):04d}" for _ in range(pool_size)]

    patient_genders = np.random.choice(["Male", "Female", "Other"], p=[0.48, 0.49, 0.03], size=num_patients)
    patient_names = []
    for g in patient_genders:
        if g == "Male":
            patient_names.append(f"{np.random.choice(first_names_m)} {np.random.choice(last_names)}")
        else:
            patient_names.append(f"{np.random.choice(first_names_f)} {np.random.choice(last_names)}")

    patient_ages = np.random.choice(
        [
            np.random.randint(18, 36),
            np.random.randint(36, 51),
            np.random.randint(51, 66),
            np.random.randint(66, 89),
        ],
        size=num_patients,
    )

    base_ref = datetime(2024, 1, 1)
    dobs = [(base_ref - timedelta(days=int(a * 365.25))).strftime("%Y-%m-%d") for a in patient_ages]
    created_dates = [(base_ref - timedelta(days=int(np.random.randint(10, 800)))).strftime("%Y-%m-%d") for _ in range(num_patients)]

    insurance_providers = [
        "Blue Cross Blue Shield", "Aetna Health", "UnitedHealthcare",
        "Medicare", "Medicaid", "Cigna", "Humana"
    ]

    df_patients = pd.DataFrame({
        "patient_id": [f"P_{i+1:05d}" for i in range(num_patients)],
        "name": patient_names,
        "dob": dobs,
        "age": patient_ages,
        "gender": patient_genders,
        "blood_group": np.random.choice(BLOOD_GROUPS, num_patients),
        "contact": np.random.choice(phones, num_patients),
        "address": np.random.choice(streets, num_patients),
        "insurance_provider": np.random.choice(insurance_providers, num_patients),
        "emergency_contact": np.random.choice(phones, num_patients),
        "created_at": created_dates,
    })
    patient_ids = df_patients["patient_id"].tolist()

    # 5. Medications Catalog (200 records)
    medications = []
    for idx, med_meta in enumerate(MEDICATION_CATALOG):
        med_id = f"MED_{idx+1:03d}"
        medications.append({
            "medication_id": med_id,
            "medication_name": med_meta["name"],
            "category": med_meta["category"],
            "dosage_form": med_meta["form"],
            "unit_cost": med_meta["unit_cost"],
            "reorder_threshold": med_meta["reorder"],
            "standard_daily_dose": med_meta["daily_dose"],
        })
    df_medications = pd.DataFrame(medications)
    med_ids_pool = df_medications["medication_id"].tolist()

    # 6. Pharmacy Inventory (2,500 records)
    num_inv = counts.get("pharmacy_inventory", 2500)
    inventory = []
    for i in range(num_inv):
        m_id = np.random.choice(med_ids_pool)
        h_id = np.random.choice([h["hospital_id"] for h in hospitals])
        reorder = int(np.random.randint(50, 300))
        stock = int(np.random.randint(10, 1500))
        inventory.append({
            "inventory_id": f"INV_{i+1:05d}",
            "medication_id": m_id,
            "hospital_id": h_id,
            "stock_quantity": stock,
            "batch_number": f"BATCH_{np.random.randint(1000, 9999)}",
            "expiry_date": (datetime.now() + timedelta(days=int(np.random.randint(60, 720)))).strftime("%Y-%m-%d"),
            "reorder_level": reorder,
            "last_restocked_date": (datetime.now() - timedelta(days=int(np.random.randint(5, 60)))).strftime("%Y-%m-%d"),
        })
    df_inventory = pd.DataFrame(inventory)

    # 7. Admissions (55,000+ records)
    num_admissions = counts.get("admissions", 55000)
    print(f"Generating {num_admissions:,} Inpatient Admission records...")
    
    adm_patients = np.random.choice(patient_ids, num_admissions)
    adm_docs = np.random.choice(doctor_ids, num_admissions)
    
    adm_days_offset = np.random.randint(0, 500, num_admissions)
    adm_dates = [base_ref + timedelta(days=int(d)) for d in adm_days_offset]
    
    pid_to_age = dict(zip(df_patients["patient_id"], df_patients["age"]))
    adm_ages = np.array([pid_to_age.get(p, 50) for p in adm_patients])
    adm_types = np.random.choice(ADMISSION_TYPES, p=[0.45, 0.35, 0.20], size=num_admissions)
    is_em = (adm_types == "Emergency").astype(int)
    is_urg = (adm_types == "Urgent").astype(int)

    # Clinically correlated Length of Stay
    los_values = np.clip(np.round(2.0 + (adm_ages > 65) * 1.5 + is_em * 2.5 + is_urg * 1.0 + np.random.normal(0, 0.4, num_admissions)), 1, 28).astype(int)
    disch_dates = [adm_dates[i] + timedelta(days=int(los_values[i])) for i in range(num_admissions)]

    # Clinical LACE 30-Day Readmission Risk
    lace_risk = (adm_ages > 65) * 1.5 + is_em * 2.5 + (los_values >= 5) * 2.0
    lace_prob = 1.0 / (1.0 + np.exp(-(lace_risk - 4.5) / 1.0))
    readm_values = (lace_prob >= 0.50).astype(int)

    df_admissions = pd.DataFrame({
        "admission_id": [f"ADM_{i+1:06d}" for i in range(num_admissions)],
        "patient_id": adm_patients,
        "hospital_id": [doc_lookup[d][0] for d in adm_docs],
        "doctor_id": adm_docs,
        "department_id": [doc_lookup[d][1] for d in adm_docs],
        "admission_date": [d.strftime("%Y-%m-%d") for d in adm_dates],
        "discharge_date": [d.strftime("%Y-%m-%d") for d in disch_dates],
        "length_of_stay": los_values,
        "admission_type": adm_types,
        "room_number": np.random.randint(101, 799, size=num_admissions).astype(str),
        "discharge_disposition": np.random.choice(DISCHARGE_DISPOSITIONS, p=[0.75, 0.12, 0.08, 0.03, 0.02], size=num_admissions),
        "readmitted_30d": readm_values,
    })
    admission_ids = df_admissions["admission_id"].tolist()
    adm_id_to_patient = dict(zip(df_admissions["admission_id"], df_admissions["patient_id"]))
    adm_id_to_date = dict(zip(df_admissions["admission_id"], df_admissions["admission_date"]))
    adm_id_to_doc = dict(zip(df_admissions["admission_id"], df_admissions["doctor_id"]))

    # 8. Diagnoses (75,000+ records)
    num_diagnoses = counts.get("diagnoses", 75000)
    print(f"Generating {num_diagnoses:,} Clinical Diagnosis records...")
    
    diag_adms = np.random.choice(admission_ids, num_diagnoses)
    sampled_icd_idx = np.random.choice(len(ICD10_CATALOG), num_diagnoses)
    
    diag_codes = [ICD10_CATALOG[i]["code"] for i in sampled_icd_idx]
    diag_descs = [ICD10_CATALOG[i]["description"] for i in sampled_icd_idx]
    diag_sevs = [ICD10_CATALOG[i]["severity"] for i in sampled_icd_idx]
    diag_types = np.random.choice(["Primary", "Secondary"], p=[0.60, 0.40], size=num_diagnoses)

    df_diagnoses = pd.DataFrame({
        "diagnosis_id": [f"DX_{i+1:06d}" for i in range(num_diagnoses)],
        "admission_id": diag_adms,
        "patient_id": [adm_id_to_patient[a] for a in diag_adms],
        "icd10_code": diag_codes,
        "diagnosis_description": diag_descs,
        "diagnosis_type": diag_types,
        "diagnosis_date": [adm_id_to_date[a] for a in diag_adms],
        "severity": diag_sevs,
    })

    # 9. Laboratory Results (100,000+ records)
    num_labs = counts.get("laboratory_results", 100000)
    print(f"Generating {num_labs:,} Laboratory Investigation records...")
    
    lab_adms = np.random.choice(admission_ids, num_labs)
    lab_catalog_idx = np.random.choice(len(LAB_CATALOG), num_labs)
    
    lab_names = [LAB_CATALOG[i]["name"] for i in lab_catalog_idx]
    lab_cats = [LAB_CATALOG[i]["category"] for i in lab_catalog_idx]
    lab_units = [LAB_CATALOG[i]["unit"] for i in lab_catalog_idx]
    lab_ref_ranges = [f"{LAB_CATALOG[i]['low']} - {LAB_CATALOG[i]['high']}" for i in lab_catalog_idx]
    
    lab_flags = np.random.choice(["Normal", "High", "Low", "Critical"], p=[0.70, 0.17, 0.08, 0.05], size=num_labs)
    lab_values = []
    for idx, f in enumerate(lab_flags):
        cat_item = LAB_CATALOG[lab_catalog_idx[idx]]
        if f == "Normal":
            lab_values.append(round(float(np.random.uniform(cat_item["low"], cat_item["high"])), 2))
        elif f == "High":
            lab_values.append(round(float(np.random.uniform(cat_item["high"] + 0.1, cat_item["crit_high"] * 0.95)), 2))
        elif f == "Low":
            lab_values.append(round(float(np.random.uniform(cat_item["crit_low"] * 1.05, cat_item["low"] - 0.1)), 2))
        else:
            lab_values.append(round(float(np.random.uniform(cat_item["crit_high"], cat_item["crit_high"] * 1.4)), 2))

    df_labs = pd.DataFrame({
        "lab_id": [f"LAB_{i+1:06d}" for i in range(num_labs)],
        "patient_id": [adm_id_to_patient[a] for a in lab_adms],
        "admission_id": lab_adms,
        "test_name": lab_names,
        "test_category": lab_cats,
        "test_value": lab_values,
        "reference_range": lab_ref_ranges,
        "unit": lab_units,
        "abnormal_flag": lab_flags,
        "test_date": [adm_id_to_date[a] for a in lab_adms],
    })

    # 10. Prescriptions (80,000+ records)
    num_rx = counts.get("prescriptions", 80000)
    print(f"Generating {num_rx:,} Prescription records...")
    
    rx_adms = np.random.choice(admission_ids, num_rx)
    rx_meds = np.random.choice(med_ids_pool, num_rx)
    frequencies = ["Once daily", "Twice daily", "Every 8 hours", "At bedtime", "As needed"]

    df_prescriptions = pd.DataFrame({
        "prescription_id": [f"RX_{i+1:06d}" for i in range(num_rx)],
        "patient_id": [adm_id_to_patient[a] for a in rx_adms],
        "doctor_id": [adm_id_to_doc[a] for a in rx_adms],
        "admission_id": rx_adms,
        "medication_id": rx_meds,
        "dosage": np.random.choice(["10 mg", "20 mg", "40 mg", "500 mg", "1000 mg"], num_rx),
        "frequency": np.random.choice(frequencies, num_rx),
        "duration_days": np.random.choice([7, 10, 14, 30, 90], num_rx),
        "quantity": np.random.choice([10, 30, 60, 90], num_rx),
        "prescription_date": [adm_id_to_date[a] for a in rx_adms],
        "status": np.random.choice(["Active", "Completed", "Discontinued"], p=[0.70, 0.25, 0.05], size=num_rx),
    })

    # 11. Appointments (60,000+ records)
    num_apts = counts.get("appointments", 60000)
    print(f"Generating {num_apts:,} Patient Appointment records...")
    
    apt_patients = np.random.choice(patient_ids, num_apts)
    apt_docs = np.random.choice(doctor_ids, num_apts)
    apt_dates = [base_ref + timedelta(days=int(np.random.randint(0, 480))) for _ in range(num_apts)]
    apt_statuses = np.random.choice(APPOINTMENT_STATUSES, p=[0.72, 0.14, 0.08, 0.06], size=num_apts)
    wait_times = [int(np.random.randint(8, 65)) if s == "Completed" else 0 for s in apt_statuses]

    reasons = [
        "Routine Follow-up", "Annual Health Checkup", "Chronic Disease Review",
        "Post-Operative Follow-up", "Medication Adjustment", "Chest Discomfort",
        "Respiratory Symptoms", "Diabetes Monitoring"
    ]

    df_appointments = pd.DataFrame({
        "appointment_id": [f"APT_{i+1:06d}" for i in range(num_apts)],
        "patient_id": apt_patients,
        "doctor_id": apt_docs,
        "department_id": [doc_lookup[d][1] for d in apt_docs],
        "appointment_date": [d.strftime("%Y-%m-%d") for d in apt_dates],
        "appointment_time": [f"{np.random.randint(8, 17):02d}:{np.random.choice(['00', '15', '30', '45'])}" for _ in range(num_apts)],
        "status": apt_statuses,
        "reason_for_visit": np.random.choice(reasons, num_apts),
        "waiting_time_minutes": wait_times,
    })

    # 12. Billing (55,000+ records - one per admission)
    print(f"Generating {num_admissions:,} Billing records...")
    base_charges = df_admissions["length_of_stay"] * np.random.uniform(1100, 2400, num_admissions)
    lab_charges = np.random.uniform(300, 1800, num_admissions)
    pharm_charges = np.random.uniform(150, 1200, num_admissions)
    total_bills = np.round(base_charges + lab_charges + pharm_charges, 2)
    
    ins_ratios = np.random.uniform(0.65, 0.95, num_admissions)
    ins_covered = np.round(total_bills * ins_ratios, 2)
    patient_dues = np.round(total_bills - ins_covered, 2)

    df_billing = pd.DataFrame({
        "bill_id": [f"BILL_{i+1:06d}" for i in range(num_admissions)],
        "patient_id": df_admissions["patient_id"],
        "admission_id": df_admissions["admission_id"],
        "bill_date": df_admissions["discharge_date"],
        "total_amount": total_bills,
        "insurance_covered": ins_covered,
        "patient_payable": patient_dues,
        "payment_status": np.random.choice(PAYMENT_STATUSES, p=[0.82, 0.14, 0.04], size=num_admissions),
        "payment_method": np.random.choice(["Commercial Insurance", "Medicare", "Credit Card", "Direct Debit", "Cash"], num_admissions),
    })

    # Apply realistic imperfection injection for Bronze/Silver testing
    print("Injecting realistic data quality issues (duplicates, nulls, inconsistent casing, corrupt dates)...")

    df_patients_raw = inject_realistic_imperfections(
        df_patients,
        date_columns=["dob", "created_at"],
        categorical_columns=["gender", "blood_group"],
        nullable_columns=["contact", "emergency_contact", "address"],
        numeric_columns=["age"],
        duplicate_ratio=0.015,
        seed=seed,
    )

    df_admissions_raw = inject_realistic_imperfections(
        df_admissions,
        date_columns=["admission_date", "discharge_date"],
        categorical_columns=["admission_type", "discharge_disposition"],
        nullable_columns=["room_number"],
        numeric_columns=["length_of_stay"],
        duplicate_ratio=0.012,
        seed=seed + 1,
    )

    df_diagnoses_raw = inject_realistic_imperfections(
        df_diagnoses,
        date_columns=["diagnosis_date"],
        categorical_columns=["severity", "diagnosis_type"],
        nullable_columns=[],
        duplicate_ratio=0.01,
        seed=seed + 2,
    )

    df_labs_raw = inject_realistic_imperfections(
        df_labs,
        date_columns=["test_date"],
        categorical_columns=["abnormal_flag"],
        nullable_columns=["unit"],
        numeric_columns=["test_value"],
        duplicate_ratio=0.012,
        seed=seed + 3,
    )

    df_medications_raw = inject_realistic_imperfections(
        df_medications,
        categorical_columns=["category"],
        nullable_columns=["dosage_form"],
        duplicate_ratio=0.0,
        seed=seed + 4,
    )

    df_prescriptions_raw = inject_realistic_imperfections(
        df_prescriptions,
        date_columns=["prescription_date"],
        categorical_columns=["status"],
        nullable_columns=["frequency"],
        duplicate_ratio=0.01,
        seed=seed + 5,
    )

    df_appointments_raw = inject_realistic_imperfections(
        df_appointments,
        date_columns=["appointment_date"],
        categorical_columns=["status"],
        nullable_columns=["reason_for_visit"],
        duplicate_ratio=0.01,
        seed=seed + 6,
    )

    df_billing_raw = inject_realistic_imperfections(
        df_billing,
        date_columns=["bill_date"],
        categorical_columns=["payment_status", "payment_method"],
        nullable_columns=["payment_method"],
        duplicate_ratio=0.01,
        seed=seed + 7,
    )

    df_inventory_raw = inject_realistic_imperfections(
        df_inventory,
        date_columns=["expiry_date", "last_restocked_date"],
        categorical_columns=[],
        nullable_columns=["batch_number"],
        duplicate_ratio=0.01,
        seed=seed + 8,
    )

    # Persist to disk in RAW directory
    print(f"Persisting raw files to {output_dir}...")
    df_hospitals.to_csv(output_dir / "hospitals.csv", index=False)
    df_departments.to_csv(output_dir / "departments.csv", index=False)
    df_doctors.to_csv(output_dir / "doctors.csv", index=False)
    df_patients_raw.to_csv(output_dir / "patients.csv", index=False)
    df_admissions_raw.to_csv(output_dir / "admissions.csv", index=False)
    df_diagnoses_raw.to_csv(output_dir / "diagnoses.csv", index=False)
    df_prescriptions_raw.to_csv(output_dir / "prescriptions.csv", index=False)
    df_appointments_raw.to_csv(output_dir / "appointments.csv", index=False)
    df_billing_raw.to_csv(output_dir / "billing.csv", index=False)
    df_inventory_raw.to_csv(output_dir / "pharmacy_inventory.csv", index=False)

    # Multi-format: JSON datasets
    df_labs_raw.to_json(output_dir / "laboratory_results.json", orient="records")
    df_medications_raw.to_json(output_dir / "medications.json", orient="records")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "seed": seed,
        "counts": {
            "hospitals": len(df_hospitals),
            "departments": len(df_departments),
            "doctors": len(df_doctors),
            "patients": len(df_patients_raw),
            "admissions": len(df_admissions_raw),
            "diagnoses": len(df_diagnoses_raw),
            "laboratory_results": len(df_labs_raw),
            "medications": len(df_medications_raw),
            "prescriptions": len(df_prescriptions_raw),
            "appointments": len(df_appointments_raw),
            "billing": len(df_billing_raw),
            "pharmacy_inventory": len(df_inventory_raw),
        },
        "quality_defects_injected": [
            "Intentional duplicate rows (~1-1.5%)",
            "Inconsistent date representations (MM/DD/YYYY, DD-MM-YYYY, ISO)",
            "Irregular casing (UPPER, lower, leading/trailing whitespace)",
            "Missing values in optional fields (contact, room_number, units)",
            "Invalid categorical token anomalies ('UNKNOWN_VAL')",
            "Occasional invalid numerical values for outlier detection",
        ],
    }

    with open(METADATA_DIR / "generation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    total_records = sum(summary["counts"].values())
    print(f"Synthetic healthcare dataset generation complete. Total records: {total_records:,}")
    return summary


if __name__ == "__main__":
    generate_healthcare_ecosystem()
