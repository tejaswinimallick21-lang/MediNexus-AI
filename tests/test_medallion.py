"""
Tests for Silver and Gold Medallion transformations in MediNexus AI.
"""

import pytest
import pandas as pd
import numpy as np

from src.medallion.silver import transform_silver_table
from src.medallion.pipeline import run_full_medallion_pipeline
from src.utils.database import query_df, table_exists


def test_silver_patient_cleansing():
    """Verify Silver transformation deduplicates and standardizes patient records."""
    df_raw = pd.DataFrame({
        "patient_id": ["P_001", "P_001", "P_002", "P_003"],
        "name": ["John Doe", "John Doe", "Jane Smith", "Bob  "],
        "dob": ["01/15/1985", "1985-01-15", "15-06-1990", "1970/05/20"],
        "age": [39, 39, -25, 150],  # test negative and excessive age
        "gender": ["male", "MALE", "FEMALE", "other"],
        "blood_group": ["o+", "O+", "a-", "b+"],
        "contact": [None, None, "555-1234", None],
        "created_at": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"],
    })

    df_clean, report = transform_silver_table("patients", df_raw, run_id="test_run")

    # 1. Verify deduplication
    assert len(df_clean) == 3
    assert df_clean["patient_id"].duplicated().sum() == 0

    # 2. Verify gender standardization
    assert set(df_clean["gender"]) == {"Male", "Female", "Other"}

    # 3. Verify age clamping (negative age fixed to positive)
    assert (df_clean["age"] >= 0).all()
    assert (df_clean["age"] <= 110).all()

    # 4. Verify blood group uppercase
    assert set(df_clean["blood_group"]) == {"O+", "A-", "B+"}

    # 5. Verify quality score calculation
    assert report["quality_score"] > 70.0


def test_silver_admission_cleansing():
    """Verify Silver admission cleaning clamps LOS and standardizes dates."""
    df_raw = pd.DataFrame({
        "admission_id": ["ADM_001", "ADM_002"],
        "patient_id": ["P_001", "P_002"],
        "admission_date": ["15-01-2024", "2024-02-01"],
        "discharge_date": ["20-01-2024", "2024-02-05"],
        "length_of_stay": [-5, 4],  # negative LOS should be clamped
        "admission_type": ["emergency", "ELECTIVE"],
        "discharge_disposition": ["home", "transferred"],
        "room_number": [None, "204"],
    })

    df_clean, report = transform_silver_table("admissions", df_raw, run_id="test_run")

    assert (df_clean["length_of_stay"] >= 1).all()
    assert set(df_clean["admission_type"]) == {"Emergency", "Elective"}
    assert set(df_clean["discharge_disposition"]) == {"Home", "Transferred"}
