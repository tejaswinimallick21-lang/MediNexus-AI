"""
Linking several uploads: relationship discovery, point-in-time consolidation, model selection,
the insights report, and proof that sandboxes never change the live lakehouse.
"""

import io

import numpy as np
import pandas as pd
import pytest

from backend.app.schemas.data_platform import LinkDiscovery, UploadDetail
from backend.app.services import data_platform
from backend.tests.conftest import assert_contract, assert_error
from backend.tests.test_data_platform import wait
from src.utils.database import query_df_strict


@pytest.fixture(autouse=True)
def sandbox_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(data_platform, "UPLOADS_DIR", tmp_path / "uploads")
    yield tmp_path


def linked_tables(n_patients: int = 300, n_adm: int = 900, seed: int = 5):
    rng = np.random.default_rng(seed)
    patients = pd.DataFrame({
        "patient_id": [f"P{i:04d}" for i in range(n_patients)],
        "age": rng.integers(20, 90, n_patients),
        "comorbidity_count": rng.integers(0, 6, n_patients),
        "gender": rng.choice(["F", "M"], n_patients),
    })
    adm_patient = rng.choice(patients["patient_id"], n_adm)
    admit = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 365, n_adm), unit="D")
    p = patients.set_index("patient_id").loc[adm_patient]
    risk = 0.03 * p["comorbidity_count"].to_numpy() + 0.004 * (p["age"].to_numpy() - 20)
    readm30 = (rng.random(n_adm) < risk).astype(int)
    admissions = pd.DataFrame({
        "admission_id": [f"A{i:05d}" for i in range(n_adm)], "patient_id": adm_patient, "admit_date": admit.strftime("%Y-%m-%d"),
        "ward": rng.choice(["General", "ICU", "Cardiology"], n_adm), "readmitted_30d": readm30,
        "readmitted_7d": readm30 * (rng.random(n_adm) < 0.4),  # sibling outcome
    })
    # 1-3 diagnoses per admission; the last one is dated AFTER the admission (must be ignored point-in-time)
    rows = []
    for a, d in zip(admissions["admission_id"], admit):
        k = int(rng.integers(1, 4))
        for j in range(k):
            rows.append({"diag_id": f"D{len(rows):06d}", "admission_id": a, "diag_date": (d - pd.Timedelta(days=int(rng.integers(0, 30)))).strftime("%Y-%m-%d"),
                         "category": rng.choice(["Cardiac", "Respiratory", "Renal"])})
        rows.append({"diag_id": f"D{len(rows):06d}", "admission_id": a, "diag_date": (d + pd.Timedelta(days=10)).strftime("%Y-%m-%d"), "category": "FUTURE"})
    diagnoses = pd.DataFrame(rows)
    billing = pd.DataFrame({"bill_id": [f"B{i:05d}" for i in range(n_adm)], "admission_id": admissions["admission_id"],
                            "total_cost": np.round(rng.uniform(500, 9000, n_adm), 2)})
    return {"patients.csv": patients, "admissions.csv": admissions, "diagnoses.csv": diagnoses, "billing.csv": billing}


def upload_all(c, tables) -> dict:
    ids = {}
    for name, df in tables.items():
        r = c.post("/api/data/uploads", files={"file": (name, io.BytesIO(df.to_csv(index=False).encode()), "text/csv")})
        assert r.status_code == 202, r.text
        assert wait(r.json()["job_id"]).status == "succeeded"
        ids[name] = r.json()["upload"]["upload_id"]
    return ids


def live_snapshot():
    tables = query_df_strict("SELECT table_name FROM information_schema.tables ORDER BY 1")["table_name"].tolist()
    counts = {t: int(query_df_strict(f'SELECT COUNT(*) AS n FROM "{t}"').iloc[0]["n"]) for t in tables if t.startswith(("gold_", "silver_", "sim_"))}
    return tables, counts


def test_link_consolidate_predict_report_and_isolation(login):
    before = live_snapshot()
    c = login("admin")
    ids = upload_all(c, linked_tables())

    disc = assert_contract(c.post("/api/data/links/discover", json={"upload_ids": list(ids.values())}), LinkDiscovery, "data_link_discovery")
    assert disc["suggested_base"] == "admissions"
    pairs = {(r["from_table"], r["from_column"], r["to_table"], r["to_column"]) for r in disc["relationships"]}
    assert ("admissions", "patient_id", "patients", "patient_id") in pairs
    assert any(r["from_table"] == "diagnoses" and r["to_column"] == "admission_id" for r in disc["relationships"])

    acc = c.post("/api/data/links/consolidate", json={"upload_ids": list(ids.values()), "base_table": "admissions"})
    assert acc.status_code == 202, acc.text
    assert wait(acc.json()["job_id"]).status == "succeeded"
    uid = acc.json()["upload"]["upload_id"]

    d = assert_contract(c.get(f"/api/data/uploads/{uid}"), UploadDetail, "data_consolidated_detail")
    assert d["kind"] == "consolidated" and d["rows"] == 900
    steps = {s["table"]: s for s in d["lineage"]["steps"]}
    assert set(steps) == {"patients", "diagnoses", "billing"}
    assert steps["diagnoses"]["point_in_time"] is True
    cols = {col["name"] for col in d["cleaning"]["columns"]}
    assert "diagnoses_category_future_count" not in cols  # the future-dated diagnosis never reached the features
    assert "readmitted_30d" in d["suggested_targets"]

    job = c.post(f"/api/data/uploads/{uid}/predict", json={"target": "readmitted_30d", "exclude": ["billing_total_cost"]})
    assert job.status_code == 202, job.text
    assert wait(job.json()["job_id"]).status == "succeeded"
    d = assert_contract(c.get(f"/api/data/uploads/{uid}"), UploadDetail, "data_consolidated_insights")
    pred = d["predictions"][0]
    reasons = {e["column"]: e["reason"] for e in pred["excluded"]}
    assert reasons["readmitted_7d"].startswith("sibling outcome")
    assert reasons["billing_total_cost"] == "excluded by you"
    assert pred["selected_model"] in ("Logistic regression", "Gradient boosting")
    assert sum(m["selected"] for m in pred["model_comparison"]) == 1

    report = c.get(f"/api/data/uploads/{uid}/report.html")
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/html")
    assert "How the tables were linked" in report.text and "<script" not in report.text
    assert "default-src 'none'" in report.headers["content-security-policy"]

    for upload_id in [uid, *ids.values()]:
        assert c.delete(f"/api/data/uploads/{upload_id}").status_code == 204
    assert live_snapshot() == before  # uploads, consolidation and deletion never touch the live lakehouse


def test_link_validation(login):
    c = login("admin")
    assert_error(c.post("/api/data/links/discover", json={"upload_ids": ["a" * 32]}), 422, "validation_error")
    assert_error(c.post("/api/data/links/discover", json={"upload_ids": ["../../etc", "b" * 32]}), 422, "validation_error")
    assert_error(c.post("/api/data/links/discover", json={"upload_ids": ["a" * 32, "b" * 32]}), 404, "upload_not_found")
    assert_error(login("analyst").post("/api/data/links/discover", json={"upload_ids": ["a" * 32, "b" * 32]}), 403, "forbidden")


def test_same_identifier_gets_same_token_across_uploads(login):
    c = login("admin")
    df = pd.DataFrame({"ssn": ["123-45-6789", "987-65-4321"] * 30, "v": range(60)})
    ids = upload_all(c, {"a.csv": df, "b.csv": df})
    tokens = [set(pd.read_parquet(data_platform._dir(i) / "silver.parquet")["ssn"]) for i in ids.values()]
    assert tokens[0] == tokens[1] and not any(t.startswith("123") for t in tokens[0])
