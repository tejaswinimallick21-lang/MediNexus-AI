"""Security & Infrastructure workspace routes (/api/security/*, /api/knowledge/*): admin only."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile

from backend.app.core.deps import current_user, require_page
from backend.app.core.pagination import Page, PageParams, page_params
from backend.app.core.users import UserRecord
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.security import (
    AccessMatrix,
    AiGovernance,
    AuditEvent,
    AuditSummary,
    InfraHealth,
    KnowledgeLibrary,
    Posture,
    SearchComparison,
    SearchIn,
)
from backend.app.services import knowledge, security

guard = [Depends(require_page("it"))]
router = APIRouter(prefix="/security", tags=["security"], responses=ERROR_RESPONSES, dependencies=guard)
knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"], responses=ERROR_RESPONSES, dependencies=guard)


@router.get("/posture", response_model=Posture)
def posture() -> Posture:
    return security.get_posture()


@router.get("/audit", response_model=Page[AuditEvent])
def audit(params: PageParams = Depends(page_params), action: Optional[str] = Query(None, max_length=60), status: Optional[str] = Query(None, max_length=20),
          user: Optional[str] = Query(None, max_length=120), days: int = Query(7, ge=1, le=365)) -> Page[AuditEvent]:
    return security.list_audit(params, action, status, user, days)


@router.get("/audit/summary", response_model=AuditSummary)
def audit_summary(days: int = Query(7, ge=1, le=90)) -> AuditSummary:
    return security.audit_summary(days)


@router.get("/access", response_model=AccessMatrix)
def access() -> AccessMatrix:
    return security.access_matrix()


@router.get("/infra", response_model=InfraHealth)
def infra() -> InfraHealth:
    return security.infra_health()


@router.get("/ai", response_model=AiGovernance)
def ai(days: int = Query(7, ge=1, le=90)) -> AiGovernance:
    return security.ai_governance(days)


@knowledge_router.get("/documents", response_model=KnowledgeLibrary)
def documents() -> KnowledgeLibrary:
    return knowledge.library()


@knowledge_router.post("/documents", response_model=KnowledgeLibrary, status_code=201)
async def upload(file: UploadFile = File(...), user: UserRecord = Depends(current_user)) -> KnowledgeLibrary:
    return await knowledge.upload(file, user)


@knowledge_router.delete("/documents/{doc_id}", status_code=204, response_class=Response)
def delete(doc_id: str = Path(..., max_length=60), user: UserRecord = Depends(current_user)) -> Response:
    knowledge.delete(doc_id, user)
    return Response(status_code=204)


@knowledge_router.post("/search", response_model=SearchComparison)
def search(body: SearchIn) -> SearchComparison:
    return knowledge.compare(body.query, body.k)


@knowledge_router.get("/benchmark", response_model=Dict[str, Any])
def benchmark() -> Dict[str, Any]:
    return knowledge.benchmark_results()


@knowledge_router.post("/benchmark", response_model=Dict[str, Any])
def run_benchmark() -> Dict[str, Any]:
    return knowledge.benchmark_results(run=True)
