from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobOut(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    progress_pct: int
    stage: str
    logs: List[str]
    created_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
