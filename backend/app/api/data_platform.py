"""Data Engineering workspace routes (/api/data/*): admin only."""

from pathlib import Path as FsPath

from fastapi import APIRouter, Depends, File, Path, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from backend.app.core.deps import current_user, require_page
from backend.app.jobs import runner
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.core.users import UserRecord
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.data_platform import (
    ConsolidateIn,
    FeedRun,
    FeedStatus,
    ForecastIn,
    JobAccepted,
    LinkDiscovery,
    LinkIn,
    PredictIn,
    UploadAccepted,
    UploadDetail,
    UploadSummary,
)
from backend.app.services import data_feed, data_platform

router = APIRouter(prefix="/data", tags=["data-engineering"], responses=ERROR_RESPONSES, dependencies=[Depends(require_page("data"))])
UploadId = Path(..., pattern="^[0-9a-f]{32}$")


@router.post("/uploads", response_model=UploadAccepted, status_code=202)
async def upload(file: UploadFile = File(...), user: UserRecord = Depends(current_user)) -> UploadAccepted:
    return await data_platform.create_upload(file, user)


@router.get("/uploads", response_model=Page[UploadSummary])
def uploads(params: PageParams = Depends(page_params)) -> Page[UploadSummary]:
    return data_platform.list_uploads(params)


@router.get("/uploads/{upload_id}", response_model=UploadDetail)
def upload_detail(upload_id: str = UploadId) -> UploadDetail:
    return data_platform.get_upload(upload_id)


@router.delete("/uploads/{upload_id}", status_code=204, response_class=Response)
def delete_upload(upload_id: str = UploadId, user: UserRecord = Depends(current_user)) -> Response:
    data_platform.delete_upload(upload_id, user)
    return Response(status_code=204)


@router.get("/uploads/{upload_id}/clean.csv", response_class=FileResponse)
def download_clean(upload_id: str = UploadId, user: UserRecord = Depends(current_user)) -> FileResponse:
    path = data_platform.clean_csv_path(upload_id, user)
    name = FsPath(data_platform.get_upload(upload_id).filename).stem + "_clean.csv"
    return FileResponse(path, media_type="text/csv", filename=name)


@router.post("/uploads/{upload_id}/predict", response_model=JobAccepted, status_code=202)
def predict(body: PredictIn, upload_id: str = UploadId, user: UserRecord = Depends(current_user)) -> JobAccepted:
    return data_platform.start_prediction(upload_id, body.target, user, body.exclude)


@router.post("/uploads/{upload_id}/forecast", response_model=JobAccepted, status_code=202)
def forecast(body: ForecastIn, upload_id: str = UploadId, user: UserRecord = Depends(current_user)) -> JobAccepted:
    return data_platform.start_forecast(upload_id, body, user)


@router.get("/uploads/{upload_id}/report.html", response_class=HTMLResponse)
def report(upload_id: str = UploadId, user: UserRecord = Depends(current_user)) -> HTMLResponse:
    html = data_platform.report_html(upload_id, user)
    name = FsPath(data_platform.get_upload(upload_id).filename).stem + "_insights_report.html"
    # Opens in the browser; the page's own Save / Print to PDF works offline (no scripts, no external assets)
    return HTMLResponse(html, headers={"Content-Disposition": f'inline; filename="{name}"', "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@router.post("/links/discover", response_model=LinkDiscovery)
def discover_links(body: LinkIn) -> LinkDiscovery:
    return data_platform.discover_links(body.upload_ids)


@router.post("/links/consolidate", response_model=UploadAccepted, status_code=202)
def consolidate(body: ConsolidateIn, user: UserRecord = Depends(current_user)) -> UploadAccepted:
    return data_platform.start_consolidation(body, user)


# ---- live data feed --------------------------------------------------------------------------

@router.get("/feed", response_model=FeedStatus)
def feed() -> FeedStatus:
    s = data_feed.feed_status()
    redate, release = s.get("redate") or {}, s.get("release") or {}
    return FeedStatus(
        enabled=s["enabled"], released_through=release.get("released_through"), held_back_days=release.get("held_back_days"),
        redated_end=redate.get("redated_end"), original_cutoff=redate.get("original_cutoff"), shift_days=redate.get("shift_days"),
        next_run_at=s["next_run_at"], runs=[FeedRun(**r) for r in s["runs"]],
    )


@router.post("/feed/refresh", response_model=JobAccepted, status_code=202)
def refresh_feed(user: UserRecord = Depends(current_user)) -> JobAccepted:
    """Release records up to now and rebuild the lakehouse (runs as a background job)."""
    active = runner.active_job("data_feed")
    job = active or runner.submit("data_feed", user.email, lambda ctx: data_feed.run_refresh("manual", ctx, user.email))
    return JobAccepted(job_id=job.job_id)
