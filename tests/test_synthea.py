"""
Tests for the Synthea source adapter, outcome derivation, and silver cleansing fixes.
"""

import numpy as np
import pandas as pd
import pytest

from config.constants import GOLD_DATA_DIR
from src.ingestion.synthea_adapter import _first_match, REASON_TO_DEPARTMENT, SNOMED_TO_ICD10, LAB_REFERENCE
from src.medallion.gold import derive_unplanned_readmissions
from src.medallion.silver import clean_category_series, clean_date_series


def _adm(pid, start, stop, reason, adm_type="Elective", disposition="Home"):
    return {
        "admission_id": f"{pid}_{start}", "patient_id": pid, "admission_reason": reason,
        "admission_type": adm_type, "discharge_disposition": disposition,
        "_adm_ts": pd.Timestamp(start), "_dis_ts": pd.Timestamp(stop),
    }


def test_unplanned_readmission_rules():
    """Readmission labels follow the planned / transfer / death exclusions."""
    df = pd.DataFrame([
        _adm("A", "2020-01-01", "2020-01-03", "Pneumonia"),
        _adm("A", "2020-01-13", "2020-01-15", "Heart failure"),           # different reason, 10 days -> unplanned
        _adm("B", "2020-01-01", "2020-01-02", "Lung cancer"),
        _adm("B", "2020-01-16", "2020-01-17", "Lung cancer"),             # same reason, elective -> planned
        _adm("C", "2020-01-01", "2020-01-05", "COVID-19"),
        _adm("C", "2020-01-05 06:00", "2020-01-09", "ICU"),               # < 24h after discharge -> transfer
        _adm("D", "2020-01-01", "2020-01-04", "Sepsis", disposition="Deceased"),
        _adm("D", "2020-01-10", "2020-01-12", "Sepsis2"),                 # cannot follow a death
        _adm("E", "2020-01-01", "2020-01-02", "Asthma"),
        _adm("E", "2020-01-20", "2020-01-22", "Asthma", adm_type="Emergency"),  # same reason via ED -> unplanned
        _adm("F", "2020-01-01", "2020-01-02", "Fracture"),
        _adm("F", "2020-03-15", "2020-03-16", "Fall"),                    # outside 30-day window
    ])
    out = derive_unplanned_readmissions(df, data_end=pd.Timestamp("2020-02-10")).set_index("admission_id")

    assert out.loc["A_2020-01-01", "readmitted_30d"] == 1
    assert out.loc["B_2020-01-01", "readmitted_30d"] == 0
    assert out.loc["B_2020-01-01", "planned_readmission_30d"] == 1
    assert out.loc["B_2020-01-01", "readmitted_30d_all_cause"] == 1
    assert out.loc["C_2020-01-01", "readmitted_30d"] == 0
    assert out.loc["D_2020-01-01", "readmitted_30d"] == 0
    assert out.loc["E_2020-01-01", "readmitted_30d"] == 1
    assert out.loc["F_2020-01-01", "readmitted_30d"] == 0
    # Follow-up completeness relative to the end of observed data
    assert out.loc["A_2020-01-01", "followup_complete"] == 1
    assert out.loc["F_2020-03-15", "followup_complete"] == 0


def test_clean_category_series_keeps_missing_as_default():
    """Missing categorical values must not become the literal string 'Nan'."""
    s = pd.Series(["emergency", "  ELECTIVE  ", np.nan, None])
    out = clean_category_series(s, "Unknown")
    assert list(out) == ["Emergency", "Elective", "Unknown", "Unknown"]


def test_clean_date_series_respects_source_formats():
    """Day-first dashed dates and month-first slashed dates both resolve to the same ISO date."""
    s = pd.Series(["2020-03-05", "05-03-2020", "03/05/2020", "2020/03/05 00:00:00"])
    assert set(clean_date_series(s)) == {"2020-03-05"}


def test_reason_to_department_mapping():
    reasons = pd.Series(["COVID-19", "Malignant neoplasm of breast (disorder)", "Chronic congestive heart failure (disorder)",
                         "Admission to intensive care unit (procedure)", "Impacted molars", "Something else"])
    depts = list(_first_match(reasons, REASON_TO_DEPARTMENT, "Internal Medicine"))
    assert depts == ["Pulmonology", "Oncology", "Cardiology", "Critical Care", "General Surgery", "Internal Medicine"]


def test_reference_catalogs_are_consistent():
    """Crosswalk severities and lab reference intervals are well-formed."""
    assert all(sev in {"Mild", "Moderate", "Severe"} for _, sev in SNOMED_TO_ICD10.values())
    for name, category, low, high, crit_low, crit_high in LAB_REFERENCE.values():
        assert low <= high
        assert crit_low is None or crit_low <= low
        assert crit_high is None or crit_high >= high


def test_gold_outcome_risk_snapshots():
    """12-month outcome risk: labels only in the training snapshot, one year before the scoring snapshot."""
    path = GOLD_DATA_DIR / "gold_outcome_risk.parquet"
    if not path.exists():
        pytest.skip("Gold layer not built yet")
    df = pd.read_parquet(path)
    train, score = df[df["snapshot"] == "train"], df[df["snapshot"] == "score"]
    assert len(train) and len(score) and score["patient_id"].is_unique
    assert score[["hospitalized_12m", "died_12m"]].isna().all().all()  # the future is not known
    assert train["hospitalized_12m"].notna().all() and 0.0 < train["died_12m"].mean() < 0.2
    gap = (pd.to_datetime(score["index_date"].iloc[0]) - pd.to_datetime(train["index_date"].iloc[0])).days
    assert gap == 365
