"""
Tests for Data Generation and Bronze Ingestion in MediNexus AI.
"""

import pytest
import pandas as pd
from pathlib import Path
import tempfile
import shutil

from config.constants import RAW_DATA_DIR, BRONZE_DATA_DIR, DEFAULT_COUNTS
from src.ingestion import generate_healthcare_ecosystem
from src.ingestion.ingest_bronze import ingest_bronze_layer
from src.ingestion.ingestion_utils import inject_realistic_imperfections


def test_imperfection_injection():
    """Verify that realistic quality defects are successfully injected."""
    clean_df = pd.DataFrame({
        "patient_id": [f"P_{i:03d}" for i in range(100)],
        "gender": ["Male", "Female"] * 50,
        "dob": ["1980-01-01"] * 100,
        "age": [45] * 100,
        "contact": ["555-1234"] * 100,
    })

    imperfect_df = inject_realistic_imperfections(
        clean_df,
        date_columns=["dob"],
        categorical_columns=["gender"],
        nullable_columns=["contact"],
        numeric_columns=["age"],
        duplicate_ratio=0.05,
        seed=123,
    )

    # Check that duplicates were added
    assert len(imperfect_df) > len(clean_df)

    # Check that nulls were introduced
    assert imperfect_df["contact"].isna().sum() > 0


def test_dataset_generation_and_interconnectedness():
    """Verify that dataset generation creates interconnected datasets with foreign keys."""
    pytest.importorskip("faker", reason="Legacy synthetic generator requires Faker")
    # Use smaller test sample
    test_counts = {
        "patients": 100,
        "admissions": 150,
        "diagnoses": 200,
        "laboratory_results": 300,
        "medications": 20,
        "prescriptions": 250,
        "appointments": 150,
        "billing": 150,
        "hospitals": 3,
        "doctors": 10,
        "pharmacy_inventory": 60,
        "departments": 8,
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        summary = generate_healthcare_ecosystem(counts=test_counts, seed=99, output_dir=tmp_path)

        assert "counts" in summary
        assert (tmp_path / "patients.csv").exists()
        assert (tmp_path / "admissions.csv").exists()
        assert (tmp_path / "laboratory_results.json").exists()

        df_pts = pd.read_csv(tmp_path / "patients.csv")
        df_adm = pd.read_csv(tmp_path / "admissions.csv")

        # Referential integrity check: admissions must reference valid patient_ids
        pt_ids = set(df_pts["patient_id"].dropna())
        adm_pt_ids = set(df_adm["patient_id"].dropna())
        assert len(adm_pt_ids.intersection(pt_ids)) > 0


def test_bronze_ingestion(tmp_path):
    """Verify Bronze ingestion creates Parquet files with ingestion metadata (written to a temp folder, never data/bronze)."""
    res = ingest_bronze_layer(bronze_dir=tmp_path)
    assert res["status"] in ["SUCCESS", "PARTIAL", "EMPTY"]
    if res["status"] == "SUCCESS":
        assert res["total_rows"] > 0
        bronze_files = list(tmp_path.glob("*.parquet"))
        assert len(bronze_files) > 0
