from fastapi import APIRouter, Depends

from backend.app.core.deps import current_user
from backend.app.core.errors import APIError
from backend.app.core.users import UserRecord
from backend.app.jobs import runner
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.jobs import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"], responses=ERROR_RESPONSES)


@router.get("/{job_id}", response_model=JobOut)
def job_status(job_id: str, user: UserRecord = Depends(current_user)) -> JobOut:
    job = runner.get(job_id)
    # Only the user who started a job can read it (same 404 either way: no job-id probing)
    if job is None or job.owner != user.email:
        raise APIError(404, "job_not_found", "No such job.")
    return job.to_out()
