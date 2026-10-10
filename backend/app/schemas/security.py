"""Schemas for the Security & Infrastructure workspace (admin only)."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PostureCheck(BaseModel):
    id: str
    area: str
    title: str
    status: Literal["pass", "warn", "fail"]
    detail: str
    fix: Optional[str] = None


class Posture(BaseModel):
    score: int
    passed: int
    warnings: int
    failures: int
    environment: str
    checks: List[PostureCheck]


class AuditEvent(BaseModel):
    log_id: str
    timestamp: str
    username: str
    role: str
    action: str
    resource: str
    status: str
    details: str


class CountRow(BaseModel):
    label: str
    count: int


class DayRow(BaseModel):
    day: str
    events: int
    failed_logins: int
    denied: int


class AuditSummary(BaseModel):
    window_days: int
    total_events: int
    failed_logins: int
    access_denied: int
    lockouts: int
    patient_record_views: int
    by_action: List[CountRow]
    by_day: List[DayRow]
    failed_login_accounts: List[CountRow]
    denied_resources: List[CountRow]
    locked_now: Dict[str, int]
    actions: List[str]


class AccessMatrix(BaseModel):
    roles: List[Dict[str, Any]]
    workspaces: List[Dict[str, Any]]
    agents: List[Dict[str, Any]]
    approvals: List[Dict[str, Any]]


class TableStat(BaseModel):
    name: str
    layer: str
    rows: int


class StorageRow(BaseModel):
    label: str
    path: str
    size_mb: float
    files: int


class InfraHealth(BaseModel):
    api_version: str
    environment: str
    python: str
    platform: str
    uptime_minutes: int
    database_path: str
    database_size_mb: float
    tables: List[TableStat]
    layer_rows: Dict[str, int]
    storage: List[StorageRow]
    active_models: int
    models_last_trained: Optional[str] = None
    active_jobs: List[str]
    sweep_next_run: str
    sweep_last_status: Optional[str] = None
    llm_provider: str
    embeddings: str
    knowledge_documents: int
    knowledge_chunks: int


class AgentUsage(BaseModel):
    agent: str
    queries: int
    fallbacks: int
    avg_latency_ms: float
    tool_calls: int


class AiGovernance(BaseModel):
    provider: str
    caps: Dict[str, Any]
    embeddings: str
    window_days: int
    usage: List[AgentUsage]
    top_tools: List[CountRow]
    proposals: List[Dict[str, Any]]
    approval_rate_pct: Optional[float] = None
    sweep_runs: List[Dict[str, Any]]
    guardrails: List[str]


class KnowledgeDoc(BaseModel):
    doc_id: str
    title: str
    policy_id: str
    category: str
    filename: str
    source: Literal["library", "uploaded"]
    sections: int
    words: int


class KnowledgeLibrary(BaseModel):
    documents: List[KnowledgeDoc]
    chunks: int
    dense_model: str
    dense_error: Optional[str] = None


class SearchIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    k: int = Field(3, ge=1, le=10)


class SearchHit(BaseModel):
    title: str
    policy_id: str
    section: str
    filename: str
    source: str
    text: str
    score: float
    bm25: float
    dense: float
    bm25_rank: Optional[int] = None
    dense_rank: Optional[int] = None


class SearchComparison(BaseModel):
    query: str
    identifier_query: bool
    dense_model: str
    results: Dict[str, List[SearchHit]]
