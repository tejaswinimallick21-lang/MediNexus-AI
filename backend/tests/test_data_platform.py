"""
Data Engineering upload sandbox: upload → Bronze/Silver/Gold → insights, access, and the ML jobs.
Uploads go to a temporary directory; the live lakehouse is only read (for drift comparison).
"""

import io
import time

import numpy as np
import pandas as pd
import pytest

from backend.app.core.pagination import Page
from backend.app.jobs import runner
from backend.app.schemas.data_platform import DatasetInfo, UploadAccepted, UploadDetail, UploadSummary
from backend.app.services import data_platform
from backend.tests.conftest import FIXTURE_DIR, assert_contract, assert_error


def messy_csv(n: int = 400, seed: int = 3) -> bytes:
    rng = np.random.default_rng(seed)
    days = pd.to_datetime("2024-01-01") + pd.to_timedelta(np.sort(rng.integers(0, max(120, n // 6), n)), unit="D")
    age = rng.integers(18, 90, n).astype(float)
    age[:3] = [150, -2, 45]  # impossible values
    cost = 2000 + age * 40 + rng.normal(0, 300, n)
    readmitted = np.where(age + rng.normal(0, 10, n) > 65, "Yes", "No")
    df = pd.DataFrame({
        "Patient ID": [f"PX{i:05d}" for i in range(n)],
        "Admit Date": days.strftime("%Y-%m-%d"),
        "Age": age,
        " Ward ": rng.choice(["Cardiology", "cardiology ", "Oncology", "ONCOLOGY", "General"], n),
        "Total Cost": [f"${c:,.2f}" for c in cost],
        "SSN": [f"{rng.integers(100, 999)}-{rng.integers(10, 99)}-{rng.integers(1000, 9999)}" for _ in range(n)],
        "Contact": [f"user{i}@example.com" for i in range(n)],
        "Readmitted": readmitted,
        "readmitted_flag_copy": (readmitted == "Yes").astype(int),  # planted leakage
        "Empty Col": [None] * n,
    })
    df = pd.concat([df, df.iloc[:5]], ignore_index=True)  # 5 exact duplicates
    return df.to_csv(index=False).encode()


@pytest.fixture(autouse=True)
def sandbox_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(data_platform, "UPLOADS_DIR", tmp_path / "uploads")
    yield tmp_path


def wait(job_id: str, timeout: float = 120) -> runner.Job:
    end = time.time() + timeout
    while time.time() < end:
        job = runner.get(job_id)
        if job and job.status in ("succeeded", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def upload(client, content: bytes = None, name: str = "admissions_export.csv"):
    return client.post("/api/data/uploads", files={"file": (name, io.BytesIO(messy_csv() if content is None else content), "text/csv")})


def test_data_workspace_is_admin_only(login, client):
    assert_error(upload(client), 401, "not_authenticated")
    assert_error(login("analyst").get("/api/data/uploads"), 403, "forbidden")
    assert_error(login("hcp").get("/api/data/uploads"), 403, "forbidden")


def test_dataset_info(login):
    from src.ingestion.oncology_dataset import status

    assert_error(login("analyst").get("/api/data/dataset"), 403, "forbidden")
    body = assert_contract(login("admin").get("/api/data/dataset"), DatasetInfo, "data_dataset")
    assert body["as_of"] == status()["as_of"]
    assert body["patients"] == body["living"] + body["deceased"] > 0
    assert sum(c["count"] for c in body["cancer_types"]) == body["patients"]
    assert [s["label"] for s in body["stages"]] == ["Stage I", "Stage II", "Stage III", "Stage IV"]
    assert body["repairs"]["encounters_after_death_dropped"] > 0 and body["known_limitations"]


def test_rejects_unsupported_and_empty_files(login):
    c = login("admin")
    assert_error(upload(c, b"hello", "notes.txt"), 422, "unsupported_file")
    assert_error(upload(c, b"", "empty.csv"), 422, "empty_file")


def test_upload_pipeline_and_insights(login):
    c = login("admin")
    accepted = assert_contract(upload(c), UploadAccepted, "data_upload_accepted", status=202)
    upload_id = accepted["upload"]["upload_id"]
    assert accepted["upload"]["status"] == "processing"
    assert wait(accepted["job_id"]).status == "succeeded"

    detail = assert_contract(c.get(f"/api/data/uploads/{upload_id}"), UploadDetail, "data_upload_detail")
    assert detail["status"] == "ready" and detail["rows"] == 400
    cols = {col["name"]: col for col in detail["cleaning"]["columns"]}
    assert "patient_id" in cols and "ward" in cols and "empty_col" not in cols
    assert cols["ssn"]["pii_masked"] and cols["contact"]["pii_masked"]
    assert cols["admit_date"]["kind"] == "datetime" and cols["total_cost"]["kind"] == "numeric"
    steps = {s["step"]: s["affected"] for s in detail["cleaning"]["steps"]}
    assert steps["Remove exact duplicate rows"] == 5
    assert steps["Remove impossible values"] == 4  # ages 150 and -2, each also in a duplicated row
    assert steps["Standardise category spellings"] > 0
    assert detail["profile"]["numeric"] and detail["summary"]
    assert len(detail["preview_rows"]) == 20
    assert all(not str(v).count("@") for row in detail["preview_rows"] for v in row if v)  # emails never shown

    listed = assert_contract(c.get("/api/data/uploads"), Page[UploadSummary], "data_uploads")
    assert listed["items"][0]["upload_id"] == upload_id

    csv = c.get(f"/api/data/uploads/{upload_id}/clean.csv")
    assert csv.status_code == 200 and "admissions_export_clean.csv" in csv.headers["content-disposition"]

    # Predict a column: leakage is excluded and the model is compared with the baseline
    job = c.post(f"/api/data/uploads/{upload_id}/predict", json={"target": "readmitted"})
    assert job.status_code == 202, job.text
    assert wait(job.json()["job_id"]).status == "succeeded"
    # Forecast rows per day from the admission date
    job = c.post(f"/api/data/uploads/{upload_id}/forecast", json={"date_column": "admit_date", "value_column": "total_cost"})
    assert job.status_code == 202, job.text
    assert wait(job.json()["job_id"]).status == "succeeded"

    detail = assert_contract(c.get(f"/api/data/uploads/{upload_id}"), UploadDetail, "data_upload_insights")
    pred = detail["predictions"][0]
    excluded = {e["column"]: e["reason"] for e in pred["excluded"]}
    assert "readmitted_flag_copy" in excluded and "patient_id" in excluded and "ssn" in excluded
    assert pred["split"].startswith("time-based") and pred["primary_metric"] == "ROC-AUC"
    assert pred["beats_baseline"]
    assert detail["forecast"]["frequency"] == "daily" and len(detail["forecast"]["forecast"]) == 28
    assert any(s.startswith("Predicting readmitted") for s in detail["summary"])

    assert c.delete(f"/api/data/uploads/{upload_id}").status_code == 204
    assert_error(c.get(f"/api/data/uploads/{upload_id}"), 404, "upload_not_found")


def test_invalid_analysis_requests(login):
    c = login("admin")
    accepted = upload(c).json()
    wait(accepted["job_id"])
    uid = accepted["upload"]["upload_id"]
    assert_error(c.post(f"/api/data/uploads/{uid}/predict", json={"target": "nope"}), 422, "unknown_column")
    assert_error(c.post(f"/api/data/uploads/{uid}/predict", json={"target": "patient_id"}), 422, "invalid_target")
    assert_error(c.post(f"/api/data/uploads/{uid}/forecast", json={"date_column": "age"}), 422, "invalid_date_column")


def test_unparseable_file_fails_cleanly(login):
    c = login("admin")
    accepted = upload(c, b"\x00\x01\x02 not json", "broken.json").json()
    assert wait(accepted["job_id"]).status == "failed"
    detail = c.get(f"/api/data/uploads/{accepted['upload']['upload_id']}").json()
    assert detail["status"] == "failed" and detail["error"].startswith("Could not read the file")
