"""
In-process background jobs for long operations (pipeline, training, RAG benchmark).

POST endpoints submit a job and return immediately with its id; clients poll
GET /api/jobs/{id}. One worker thread runs jobs in order, because the pipeline and
training both write to the single-writer DuckDB file.
"""

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from backend.app.schemas.jobs import JobOut


class JobContext:
    """Handed to the job function so it can report progress."""

    def __init__(self, job: "Job") -> None:
        self._job = job

    def progress(self, pct: int, stage: str) -> None:
        with _lock:
            self._job.progress_pct = max(0, min(100, int(pct)))
            self._job.stage = stage
            self._job.logs.append(f"[{datetime.now():%H:%M:%S}] {pct:>3}% {stage}")


class Job:
    def __init__(self, kind: str, owner: str) -> None:
        self.job_id = uuid.uuid4().hex
        self.kind = kind
        self.owner = owner
        self.status = "queued"
        self.progress_pct = 0
        self.stage = "Queued"
        self.logs: list[str] = []
        self.created_at = datetime.now()
        self.finished_at: Optional[datetime] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

    def to_out(self) -> JobOut:
        with _lock:
            return JobOut(
                job_id=self.job_id, kind=self.kind, status=self.status, progress_pct=self.progress_pct,
                stage=self.stage, logs=list(self.logs[-200:]), created_at=self.created_at,
                finished_at=self.finished_at, result=self.result, error=self.error,
            )


_lock = threading.Lock()
_jobs: Dict[str, Job] = {}
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="medinexus-job")


def submit(kind: str, owner: str, fn: Callable[[JobContext], Optional[Dict[str, Any]]]) -> Job:
    job = Job(kind, owner)
    with _lock:
        _jobs[job.job_id] = job

    def _run() -> None:
        with _lock:
            job.status, job.stage = "running", "Starting"
        try:
            result = fn(JobContext(job))
            with _lock:
                job.result = result or {}
                job.status, job.progress_pct, job.stage = "succeeded", 100, "Completed"
        except Exception as e:  # surfaced through the status endpoint
            with _lock:
                job.status, job.error, job.stage = "failed", str(e), "Failed"
                job.logs.append(traceback.format_exc(limit=3))
        finally:
            with _lock:
                job.finished_at = datetime.now()

    _executor.submit(_run)
    return job


def get(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def active_job(kind: str) -> Optional[Job]:
    with _lock:
        return next((j for j in _jobs.values() if j.kind == kind and j.status in ("queued", "running")), None)
