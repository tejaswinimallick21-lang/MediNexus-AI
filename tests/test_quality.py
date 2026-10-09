"""
Tests for Data Quality Scoring Engine in MediNexus AI.
"""

import pytest
import pandas as pd
from src.medallion.quality import compute_dataset_quality_metrics


def test_quality_metrics_calculation():
    """Verify completeness, uniqueness, and overall quality index."""
    df_raw = pd.DataFrame({
        "id": [1, 2, 2, 3, 4],  # 1 duplicate
        "val": ["A", None, "B", "C", "D"],  # 1 null
    })

    df_clean = pd.DataFrame({
        "id": [1, 2, 3, 4],  # deduplicated
        "val": ["A", "B", "C", "D"],  # imputed
    })

    metrics = compute_dataset_quality_metrics(df_raw, df_clean, primary_key="id", dataset_name="test_data")

    assert metrics["input_rows"] == 5
    assert metrics["output_rows"] == 4
    assert metrics["duplicates_removed"] == 1
    assert metrics["nulls_before"] == 1
    assert metrics["nulls_after"] == 0
    assert 70.0 <= metrics["quality_score"] <= 100.0


def test_perfect_quality_data():
    """Verify clean dataset returns high quality score."""
    df = pd.DataFrame({
        "id": list(range(50)),
        "feature": [f"val_{i}" for i in range(50)],
    })

    metrics = compute_dataset_quality_metrics(df, df, primary_key="id", dataset_name="clean_data")
    assert metrics["duplicates_removed"] == 0
    assert metrics["nulls_before"] == 0
    assert metrics["quality_score"] >= 95.0
