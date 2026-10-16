"""
Security & Infrastructure workspace (admin only).

Everything here is measured from the running system: configuration, the audit log, the database,
the file system and the agent/approval tables. Nothing is a static claim.
"""

import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.agents import actions, providers, sweep, tools as agent_tools
from backend.app.core.access import AGENT_ROLES, PAGES, ROLE_TITLES, ROLES
from backend.app.core.config import settings
from backend.app.core.errors import APIError
from backend.app.core.pagination import Page, PageParams, build_page
from backend.app.core.security import verify_password
from backend.app.core.users import list_users
from backend.app.jobs import runner
from backend.app.schemas.security import (
    AccessMatrix,
    AgentUsage,
    AiGovernance,
    AuditEvent,
    AuditSummary,
    CountRow,
    DayRow,
    InfraHealth,
    Posture,
    PostureCheck,
    StorageRow,
    TableStat,
)
from backend.app.services import auth as auth_service
from config.constants import BASE_DIR, DATA_DIR, DATABASE_PATH, LOGS_DIR, MODELS_DIR
from src.utils.database import query_df_strict

STARTED = time.time()
DEMO_PASSWORD = "MediNexus@2026"
KEY_PATTERN = re.compile(r"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}")
ROUTE_LABELS = {"/data": "Data Engineering", "/it": "Security & Infrastructure", "/doctor": "Oncology Workstation", "/pharmacy": "Pharmacy & Supply Chain",
                "/laboratory": "Laboratory Operations", "/executive": "Oncology Outcomes", "/command-center": "Analyst Command Center",
                "/reception": "Patient Access"}


def _mask(v: str) -> str:
    return f"…{v[-4:]}" if v else "not set"


def _git(*args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# ---- posture ----------------------------------------------------------------------------------------

def get_posture() -> Posture:
    prod = not settings.is_development
    checks: List[PostureCheck] = []

    def add(id, area, title, status, detail, fix=None):
        checks.append(PostureCheck(id=id, area=area, title=title, status=status, detail=detail, fix=fix))

    add("jwt_secret", "Authentication", "Session signing key",
        "pass" if not settings.jwt_secret_is_ephemeral else ("fail" if prod else "warn"),
        "A fixed secret is configured." if not settings.jwt_secret_is_ephemeral else "No MEDINEXUS_JWT_SECRET: a random key is generated per start, so every restart signs everyone out.",
        None if not settings.jwt_secret_is_ephemeral else "Set MEDINEXUS_JWT_SECRET in .env to a long random value.")
    add("cookie_flags", "Authentication", "Session cookie flags",
        "pass" if settings.cookie_secure else ("fail" if prod else "warn"),
        f"HttpOnly and SameSite=Lax are always set; Secure is {'on' if settings.cookie_secure else 'off (HTTP allowed)'}.",
        None if settings.cookie_secure else "Serve over HTTPS and set MEDINEXUS_COOKIE_SECURE=true before going live.")
    ttl = settings.jwt_ttl_minutes
    add("session_ttl", "Authentication", "Session lifetime", "pass" if ttl <= 480 else "warn" if ttl <= 720 else "fail",
        f"Sessions expire after {ttl // 60} h {ttl % 60} min.", None if ttl <= 480 else "Keep sessions to one shift (8 h) or less.")
    locked = auth_service.lockout_state()
    add("login_lockout", "Authentication", "Brute-force protection", "pass" if auth_service.MAX_FAILURES <= 5 else "warn",
        f"{auth_service.MAX_FAILURES} failed sign-ins within {auth_service.WINDOW_SECONDS // 60} min lock the account for {auth_service.LOCK_SECONDS // 60} min. "
        f"Currently locked: {len(locked)}.")
    try:
        users = [u for u in list_users() if u.active]
        demo = [u.email for u in users if verify_password(DEMO_PASSWORD, u.password_hash)]
    except Exception:
        users, demo = [], []
    add("demo_passwords", "Authentication", "Default passwords", "pass" if not demo else ("fail" if prod else "warn"),
        f"{len(demo)} of {len(users)} accounts still use the documented demo password." if demo else "No account uses the demo password.",
        "Each of these people should sign in and use Change password, or an admin can reset them in Security → People." if demo else None)
    origins = settings.cors_origins
    add("cors", "Network", "Cross-origin access", "pass" if all(o.startswith("http://localhost") for o in origins) and "*" not in origins else "fail",
        f"Allowed origins: {', '.join(origins) or 'none (same-origin only)'}.")
    add("security_headers", "Network", "Security headers", "pass",
        "nosniff, frame-deny, no-referrer, no-store and a restrictive Permissions-Policy are sent on every API response"
        + (" plus HSTS." if settings.cookie_secure else "; HSTS is added once HTTPS is enabled."))

    tracked = _git("ls-files")
    if tracked is None:
        add("secrets_git", "Secrets", "No secrets in version control", "warn", "Git is not available, so tracked files could not be scanned.")
    else:
        leaks = []
        for rel in tracked.splitlines():
            p = BASE_DIR / rel
            if p.suffix.lower() in {".py", ".ts", ".tsx", ".json", ".md", ".txt", ".env", ".example", ".yml", ".yaml", ".toml", ".cfg", ".ini"} or p.name.startswith(".env"):
                try:
                    if p.stat().st_size < 2_000_000 and KEY_PATTERN.search(p.read_text(encoding="utf-8", errors="ignore")):
                        leaks.append(rel)
                except OSError:
                    continue
        ignored = _git("check-ignore", ".env") is not None
        add("secrets_git", "Secrets", "No secrets in version control", "fail" if leaks else ("pass" if ignored else "warn"),
            f"Key-like strings found in tracked files: {', '.join(leaks)}." if leaks else
            f"Scanned {len(tracked.splitlines())} tracked files: no API keys. .env is {'ignored by git' if ignored else 'NOT ignored by git'}.",
            "Remove the key from the file, rotate it with the provider, and keep keys only in .env." if leaks else None)

    provider = providers.active_provider()
    env_file = BASE_DIR / ".env"
    key_name = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(provider)
    if key_name:
        in_file = env_file.exists() and key_name in env_file.read_text(encoding="utf-8", errors="ignore")
        add("llm_key", "Secrets", "AI provider key storage", "pass" if in_file else "warn",
            f"{providers.provider_label()} uses {key_name} ({_mask(os.getenv(key_name, ''))}) from {'the gitignored .env file' if in_file else 'a machine environment variable'}.",
            None if in_file else "Keep provider keys in the project .env (gitignored) so they are scoped to this app.")
    else:
        add("llm_key", "Secrets", "AI provider key storage", "pass", "No AI provider key configured; agents use the rules engine.")
    pseud = (DATA_DIR / "uploads" / ".pseudonym_key").exists() or bool(os.getenv("MEDINEXUS_PSEUDONYM_KEY"))
    older = len([d for d in (DATA_DIR / "uploads").glob("*") if d.is_dir()]) if (DATA_DIR / "uploads").exists() else 0
    add("pseudonym_key", "Data protection", "Pseudonymisation key", "pass" if pseud else "warn",
        "A platform-wide key pseudonymises identifiers in uploaded datasets, so masked keys stay linkable across uploads." if pseud else
        f"No platform-wide key yet (it is created on the next dataset upload). The {older} existing sandbox(es) were masked with one-off keys, "
        "so their masked identifiers cannot be linked to other uploads.",
        None if pseud else "Re-upload datasets you want to link on masked identifiers.")
    add("agent_guardrails", "AI", "Agent guardrails", "pass",
        f"Agents act only through {len(agent_tools.TOOLS)} role-scoped tools; actions are proposals that need human approval; "
        f"patient names are stripped from tool output; max {providers.MAX_STEPS} tool rounds per question.")

    since = datetime.now() - timedelta(hours=24)
    counts = query_df_strict("SELECT action, COUNT(*) AS n FROM audit_logs WHERE timestamp >= ? GROUP BY 1", [since])
    c = dict(zip(counts["action"], counts["n"])) if not counts.empty else {}
    total = int(sum(c.values()))
    add("audit_active", "Monitoring", "Audit logging", "pass" if total else "warn",
        f"{total} events recorded in the last 24 h (sign-ins, patient-record views, data exports, agent actions).")
    failed = int(c.get("LOGIN_FAILED", 0))
    add("failed_logins", "Monitoring", "Failed sign-ins (24 h)", "pass" if failed < 10 else "warn" if failed < 50 else "fail",
        f"{failed} failed sign-ins in the last 24 h; {int(c.get('ACCOUNT_LOCKED', 0))} lockouts.")
    denied = int(c.get("ACCESS_DENIED", 0))
    add("access_denied", "Monitoring", "Blocked access attempts (24 h)", "pass" if denied < 20 else "warn",
        f"{denied} requests were blocked by role-based access control in the last 24 h.")

    passed = sum(ch.status == "pass" for ch in checks)
    warns = sum(ch.status == "warn" for ch in checks)
    fails = sum(ch.status == "fail" for ch in checks)
    score = round((passed + 0.5 * warns) / len(checks) * 100)
    return Posture(score=score, passed=passed, warnings=warns, failures=fails, environment=settings.env, checks=checks)


# ---- audit --------------------------------------------------------------------------------------

def list_audit(params: PageParams, action: Optional[str], status: Optional[str], user: Optional[str], days: int) -> Page[AuditEvent]:
    where, args = ["timestamp >= ?"], [datetime.now() - timedelta(days=days)]
    if action:
        where.append("action = ?")
        args.append(action)
    if status:
        where.append("status = ?")
        args.append(status)
    if user:
        where.append("lower(username) LIKE ?")
        args.append(f"%{user.lower()}%")
    df = query_df_strict(f"SELECT * FROM audit_logs WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                         args + [params.limit + 1, params.offset])
    rows = [AuditEvent(log_id=str(r.log_id), timestamp=str(r.timestamp)[:19].replace(" ", "T"), username=str(r.username), role=str(r.role),
                       action=str(r.action), resource=str(r.resource), status=str(r.status), details=str(r.details or "")[:300]) for r in df.itertuples()]
    return build_page(rows, params)


def audit_summary(days: int = 7) -> AuditSummary:
    since = datetime.now() - timedelta(days=days)
    by_action = query_df_strict("SELECT action, COUNT(*) AS n FROM audit_logs WHERE timestamp >= ? GROUP BY 1 ORDER BY n DESC", [since])
    by_day = query_df_strict("""
        SELECT CAST(timestamp AS DATE) AS d, COUNT(*) AS n, SUM(CASE WHEN action = 'LOGIN_FAILED' THEN 1 ELSE 0 END) AS failed,
               SUM(CASE WHEN action = 'ACCESS_DENIED' THEN 1 ELSE 0 END) AS denied
        FROM audit_logs WHERE timestamp >= ? GROUP BY 1 ORDER BY 1
    """, [since])
    failed_accounts = query_df_strict("SELECT username, COUNT(*) AS n FROM audit_logs WHERE timestamp >= ? AND action = 'LOGIN_FAILED' GROUP BY 1 ORDER BY n DESC LIMIT 8", [since])
    denied = query_df_strict("SELECT resource, COUNT(*) AS n FROM audit_logs WHERE timestamp >= ? AND action = 'ACCESS_DENIED' GROUP BY 1 ORDER BY n DESC LIMIT 8", [since])
    actions_all = query_df_strict("SELECT DISTINCT action FROM audit_logs ORDER BY 1")["action"].tolist()
    a = dict(zip(by_action["action"], by_action["n"]))
    return AuditSummary(
        window_days=days, total_events=int(sum(a.values())), failed_logins=int(a.get("LOGIN_FAILED", 0)), access_denied=int(a.get("ACCESS_DENIED", 0)),
        lockouts=int(a.get("ACCOUNT_LOCKED", 0)), patient_record_views=int(a.get("PATIENT_VIEW", 0) + a.get("PATIENT_360_VIEW", 0)),
        by_action=[CountRow(label=str(k), count=int(v)) for k, v in list(a.items())[:15]],
        by_day=[DayRow(day=str(r.d), events=int(r.n), failed_logins=int(r.failed or 0), denied=int(r.denied or 0)) for r in by_day.itertuples()],
        failed_login_accounts=[CountRow(label=str(r.username), count=int(r.n)) for r in failed_accounts.itertuples()],
        denied_resources=[CountRow(label=str(r.resource), count=int(r.n)) for r in denied.itertuples()],
        locked_now=auth_service.lockout_state(), actions=[str(x) for x in actions_all],
    )


# ---- access matrix ------------------------------------------------------------------------------

def access_matrix() -> AccessMatrix:
    pages = [{"page": k, "route": route, "label": ROUTE_LABELS.get(route, route), "roles": sorted(roles)} for k, (route, roles) in PAGES.items()]
    agent_names = {"medicare": "Nexa Care", "pharmalab": "Nexa Care · Lab & Pharmacy", "healthanalyst": "Nexa Insight", "ops": "Nexa Ops"}
    agents = []
    for key, roles in AGENT_ROLES.items():
        groups = agent_tools.AGENT_GROUPS.get(key, set())
        agents.append({"agent": key, "name": agent_names.get(key, key), "roles": sorted(roles),
                       "tools": [t.name for t in agent_tools.TOOLS if t.group in groups]})
    approvals = [{"kind": k, "label": actions.KIND_LABEL.get(k, k), "requires_page": p, "roles": sorted(PAGES[p][1])} for k, p in actions.KIND_PAGE.items()]
    return AccessMatrix(roles=[{"role": r, "title": ROLE_TITLES[r]} for r in ROLES], workspaces=pages, agents=agents, approvals=approvals)


# ---- infrastructure -----------------------------------------------------------------------------

def _display_path(p: Path) -> str:
    try:
        return str(p.relative_to(BASE_DIR))
    except ValueError:  # e.g. a database outside the project (tests use a temporary copy)
        return str(p)


def _dir_stats(path: Path) -> tuple:
    size = files = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                files += 1
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
    return round(size / 1024 / 1024, 1), files


def _layer(name: str) -> str:
    for prefix in ("bronze_", "silver_", "gold_", "sim_"):
        if name.startswith(prefix):
            return prefix[:-1]
    return "platform"


def infra_health() -> InfraHealth:
    from src.rag.hybrid import get_index

    t = query_df_strict("SELECT table_name, estimated_size FROM duckdb_tables() ORDER BY estimated_size DESC")
    tables = [TableStat(name=str(r.table_name), layer=_layer(str(r.table_name)), rows=int(r.estimated_size or 0)) for r in t.itertuples()]
    layer_rows: Dict[str, int] = {}
    for tb in tables:
        layer_rows[tb.layer] = layer_rows.get(tb.layer, 0) + tb.rows
    storage = []
    for label, path in (("Synthea source CSV", DATA_DIR / "synthea"), ("Simulated operations", DATA_DIR / "ops"), ("Upload sandboxes", DATA_DIR / "uploads"),
                        ("Knowledge uploads", DATA_DIR / "knowledge"), ("RAG cache", DATA_DIR / "rag"), ("Model artifacts", MODELS_DIR), ("Logs", LOGS_DIR),
                        ("Policy library", BASE_DIR / "documents")):
        mb, n = _dir_stats(path)
        storage.append(StorageRow(label=label, path=_display_path(path), size_mb=mb, files=n))
    reg = query_df_strict("SELECT COUNT(*) AS n, max(training_timestamp) AS last FROM model_registry WHERE status = 'ACTIVE'").iloc[0]
    runs = sweep.recent_runs(1)
    idx = get_index()
    return InfraHealth(
        api_version=settings.app_version, environment=settings.env, python=sys.version.split()[0], platform=f"{platform.system()} {platform.release()}",
        uptime_minutes=int((time.time() - STARTED) / 60), database_path=_display_path(Path(DATABASE_PATH)),
        database_size_mb=round(Path(DATABASE_PATH).stat().st_size / 1024 / 1024, 1), tables=tables[:40], layer_rows=layer_rows, storage=storage,
        active_models=int(reg["n"]), models_last_trained=str(reg["last"])[:19] if reg["last"] is not None else None,
        active_jobs=[k for k in ("sandbox_pipeline", "sandbox_predict", "sandbox_forecast", "sandbox_consolidate", "nexa_sweep") if runner.active_job(k)],
        sweep_next_run=sweep.next_run_at().isoformat(timespec="minutes"), sweep_last_status=runs[0]["status"] if runs else None,
        llm_provider=providers.provider_label(), embeddings=idx.dense_label, knowledge_documents=len({c.doc_id for c in idx.chunks}), knowledge_chunks=len(idx.chunks),
    )


# ---- AI governance ------------------------------------------------------------------------------

def ai_governance(days: int = 7) -> AiGovernance:
    from src.rag.hybrid import get_index

    since = datetime.now() - timedelta(days=days)
    q = query_df_strict("SELECT resource, status, details FROM audit_logs WHERE action = 'AGENT_QUERY' AND timestamp >= ?", [since])
    usage: Dict[str, Dict[str, Any]] = {}
    tool_counts: Dict[str, int] = {}
    for r in q.itertuples():
        u = usage.setdefault(str(r.resource), {"queries": 0, "fallbacks": 0, "lat": [], "tools": 0})
        u["queries"] += 1
        u["fallbacks"] += r.status == "FALLBACK"
        try:
            d = json.loads(r.details)
        except (TypeError, ValueError):
            continue  # older entries from the keyword agents
        u["lat"].append(float(d.get("latency_ms", 0)))
        u["tools"] += len(d.get("tools", []))
        for name in d.get("tools", []):
            tool_counts[name] = tool_counts.get(name, 0) + 1
    actions._ensure()
    props = query_df_strict("SELECT kind, status, COUNT(*) AS n FROM agent_actions GROUP BY 1, 2 ORDER BY 1, 2")
    decided = props[props["status"].isin(["executed", "rejected", "failed"])]["n"].sum()
    approved = props[props["status"].isin(["executed", "failed"])]["n"].sum()
    return AiGovernance(
        provider=providers.provider_label(),
        caps={"max_tool_rounds": providers.MAX_STEPS, "openai_max_reply_tokens": providers.OPENAI_MAX_TOKENS, "sweep_max_proposals": sweep.MAX_PROPOSALS,
              "tool_result_max_chars": agent_tools.MAX_RESULT_CHARS, "history_turns": 3},
        embeddings=get_index().dense_label, window_days=days,
        usage=[AgentUsage(agent=k, queries=v["queries"], fallbacks=v["fallbacks"], tool_calls=v["tools"],
                          avg_latency_ms=round(sum(v["lat"]) / len(v["lat"]), 0) if v["lat"] else 0.0) for k, v in sorted(usage.items())],
        top_tools=[CountRow(label=k, count=v) for k, v in sorted(tool_counts.items(), key=lambda kv: -kv[1])[:10]],
        proposals=[{"kind": str(r.kind), "label": actions.KIND_LABEL.get(str(r.kind), str(r.kind)), "status": str(r.status), "count": int(r.n)} for r in props.itertuples()],
        approval_rate_pct=round(float(approved) / float(decided) * 100, 1) if decided else None,
        sweep_runs=sweep.recent_runs(5),
        guardrails=[
            "Answers must come from tool results; agents say when data is missing instead of estimating.",
            "Tools are scoped by agent and by the user's role; patient names are removed from tool output.",
            "Actions are proposals only; execution needs approval by a role with the matching workspace.",
            "Every agent query, proposal, approval and rejection is written to the audit log (question text is not stored).",
            "Without an LLM key, or if the provider fails, a rules engine answers only what it can map to one tool.",
        ],
    )
