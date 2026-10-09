"""
Tests for Machine Learning Models and Transparency Pipeline in MediNexus AI.
"""

import pytest
import pandas as pd
from src.ml.predict import (
    predict_patient_readmission,
    predict_patient_los,
    predict_drug_demand,
    CLINICAL_DISCLAIMER,
)
from src.ml.model_registry import register_model, load_model


def test_clinical_disclaimer_presence():
    """Verify that clinical disclaimer is always present on inferences."""
    res = predict_patient_readmission("NON_EXISTENT_P99")
    assert "disclaimer" in res
    assert res["disclaimer"] == CLINICAL_DISCLAIMER


def test_model_registry_lifecycle():
    """Verify registration, persistence, and loading from the model registry."""
    dummy_model = {"weights": [0.1, 0.5, 0.9]}
    path = register_model(
        model_name="test_dummy_model",
        version="0.1.0",
        dataset="test_data",
        features=["f1", "f2"],
        metrics={"score": 0.95},
        model_obj=dummy_model,
        filename="test_dummy.joblib",
    )

    loaded = load_model("test_dummy_model")
    assert loaded is not None
    assert loaded["weights"] == [0.1, 0.5, 0.9]
