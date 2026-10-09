"""
Enterprise Audit Logging for MediNexus AI.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import pandas as pd
from config.constants import LOGS_DIR
from src.utils.database import execute_query, query_df
from src.utils.helpers import generate_uuid

AUDIT_LOG_FILE = LOGS_DIR / "audit.log"


def log_audit_event(
    username: str,
    role: str,
    action: str,
    resource: str,
    status: str = "SUCCESS",
    details: str = "",
) -> str:
    """
    Record an audit trail event in DuckDB audit_logs table and append to audit.log file.
    Does NOT log sensitive personal health information (PHI).
    """
    log_id = generate_uuid("aud")
    now = datetime.now()

    # Insert into DuckDB
    query = """
        INSERT INTO audit_logs (log_id, timestamp, username, role, action, resource, status, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        execute_query(
            query,
            [
                log_id,
                now,
                str(username),
                str(role),
                str(action),
                str(resource),
                str(status),
                str(details),
            ],
        )
    except Exception as e:
        print(f"Error persisting audit log to DuckDB: {e}")

    # Append to text audit log file
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"{now.isoformat()} | {log_id} | {username} | {role} | {action} | {resource} | {status} | {details}\n"
            )
    except Exception as e:
        print(f"Error writing to audit file: {e}")

    return log_id


def get_audit_trail(
    limit: int = 100,
    role_filter: Optional[str] = None,
    action_filter: Optional[str] = None,
) -> pd.DataFrame:
    """Retrieve filtered audit trail events for IT security monitoring."""
    where_clauses = []
    params = []

    if role_filter and role_filter != "All Roles":
        where_clauses.append("role = ?")
        params.append(role_filter)

    if action_filter and action_filter != "All Actions":
        where_clauses.append("action = ?")
        params.append(action_filter)

    query = "SELECT * FROM audit_logs"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    return query_df(query, params)
