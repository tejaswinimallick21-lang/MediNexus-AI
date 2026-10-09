"""
Database management and DuckDB connector for MediNexus AI.
"""

import duckdb
import threading
import time
from pathlib import Path
from typing import Optional, Any, List, Dict
import pandas as pd

from config.constants import DATABASE_PATH, DATABASE_DIR

_DB_LOCK = threading.RLock()

# DuckDB allows one writing process at a time. Streamlit and the FastAPI backend share the
# database file, so connections retry briefly when the other process holds the lock.
_LOCK_RETRY_SECONDS = 15.0


class DataUnavailableError(RuntimeError):
    """Raised when a strict query cannot be answered (missing table, lock timeout, bad SQL)."""


def get_db_path() -> str:
    """Return string representation of the DuckDB database path."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATABASE_PATH)


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, retrying while another process holds the file lock."""
    deadline = time.monotonic() + _LOCK_RETRY_SECONDS
    delay = 0.05
    while True:
        try:
            return duckdb.connect(get_db_path(), read_only=read_only and DATABASE_PATH.exists())
        except duckdb.IOException as e:
            if "lock" not in str(e).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


def query_df_strict(query: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
    """Read-only query that raises DataUnavailableError instead of returning an empty frame."""
    with _DB_LOCK:
        try:
            con = connect(read_only=True)
        except Exception as e:
            raise DataUnavailableError(f"Database unavailable: {e}") from e
        try:
            return con.execute(query, params or []).df()
        except Exception as e:
            raise DataUnavailableError(str(e)) from e
        finally:
            con.close()


def init_database() -> None:
    """Initialize metadata and audit tables in DuckDB."""
    with _DB_LOCK:
        con = connect()
        try:
            # Metadata table for Bronze ingestion runs
            con.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id VARCHAR,
                    source_file VARCHAR,
                    source_type VARCHAR,
                    ingestion_timestamp TIMESTAMP,
                    rows_read BIGINT,
                    rows_written BIGINT,
                    status VARCHAR,
                    error_message VARCHAR
                )
            """)

            # Metadata table for Silver data quality reports
            con.execute("""
                CREATE TABLE IF NOT EXISTS silver_quality_report (
                    report_id VARCHAR,
                    dataset VARCHAR,
                    input_rows BIGINT,
                    output_rows BIGINT,
                    duplicates_removed BIGINT,
                    nulls_before BIGINT,
                    nulls_after BIGINT,
                    invalid_values BIGINT,
                    transformations_applied VARCHAR,
                    quality_score DOUBLE,
                    run_timestamp TIMESTAMP
                )
            """)

            # Metadata table for complete Medallion pipeline executions
            con.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    pipeline_id VARCHAR,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_seconds DOUBLE,
                    bronze_count BIGINT,
                    silver_count BIGINT,
                    gold_count BIGINT,
                    avg_quality_score DOUBLE,
                    status VARCHAR,
                    error_message VARCHAR
                )
            """)

            # Metadata table for ML Model Registry
            con.execute("""
                CREATE TABLE IF NOT EXISTS model_registry (
                    model_name VARCHAR,
                    version VARCHAR,
                    training_timestamp TIMESTAMP,
                    dataset VARCHAR,
                    features VARCHAR,
                    metrics VARCHAR,
                    model_path VARCHAR,
                    status VARCHAR
                )
            """)

            # Enterprise Audit Trail
            con.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id VARCHAR,
                    timestamp TIMESTAMP,
                    username VARCHAR,
                    role VARCHAR,
                    action VARCHAR,
                    resource VARCHAR,
                    status VARCHAR,
                    details VARCHAR
                )
            """)
        finally:
            con.close()


def execute_query(query: str, params: Optional[List[Any]] = None) -> None:
    """Execute a query without expecting a return dataframe."""
    with _DB_LOCK:
        con = connect()
        try:
            if params:
                con.execute(query, params)
            else:
                con.execute(query)
        finally:
            con.close()


def query_df(query: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
    """Execute a query and return result as a pandas DataFrame."""
    with _DB_LOCK:
        con = connect()
        try:
            if params:
                return con.execute(query, params).df()
            return con.execute(query).df()
        except Exception as e:
            # Table might not exist yet
            return pd.DataFrame()
        finally:
            con.close()


def table_exists(table_name: str) -> bool:
    """Check if a table or view exists in DuckDB."""
    with _DB_LOCK:
        con = connect()
        try:
            res = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_name.lower()],
            ).fetchone()
            return bool(res and res[0] > 0)
        except Exception:
            return False
        finally:
            con.close()


def get_table_row_count(table_name: str) -> int:
    """Return row count of a table if it exists, else 0."""
    if not table_exists(table_name):
        return 0
    with _DB_LOCK:
        con = connect()
        try:
            res = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            return int(res[0]) if res else 0
        except Exception:
            return 0
        finally:
            con.close()


def save_df_to_table(table_name: str, df: pd.DataFrame, overwrite: bool = True) -> None:
    """Save or register a pandas DataFrame as a DuckDB table."""
    if df.empty:
        return
    with _DB_LOCK:
        con = connect()
        try:
            con.register("temp_df_view", df)
            if overwrite:
                con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM temp_df_view")
            else:
                con.execute(f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM temp_df_view")
                con.execute(f"INSERT INTO {table_name} SELECT * FROM temp_df_view")
            con.unregister("temp_df_view")
        finally:
            con.close()


# Ensure DB tables are ready on module import
init_database()
