"""
Bronze Layer Ingestion for MediNexus AI.
Discovers raw files (CSV, JSON), preserves source fidelity, attaches ingestion metadata,
persists Parquet in data/bronze/, registers bronze tables in DuckDB, and records audit runs.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import duckdb

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.constants import (
    RAW_DATA_DIR,
    BRONZE_DATA_DIR,
    DATASETS,
)
from src.utils.database import execute_query, save_df_to_table
from src.utils.helpers import generate_uuid
from src.utils.logging_utils import get_logger

logger = get_logger("bronze_ingestion")


def ingest_bronze_layer(
    raw_dir: Path = RAW_DATA_DIR,
    bronze_dir: Path = BRONZE_DATA_DIR,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Ingest all raw files into the Bronze Medallion layer.
    """
    run_id = run_id or generate_uuid("run_brz")
    bronze_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    total_rows = 0

    logger.info(f"Starting Bronze Ingestion (Run ID: {run_id}) from {raw_dir}")

    # Discover files in raw directory
    all_files = list(raw_dir.glob("*.csv")) + list(raw_dir.glob("*.json")) + list(raw_dir.glob("*.parquet"))

    if not all_files:
        logger.warning(f"No raw files found in {raw_dir}!")
        return {"run_id": run_id, "status": "EMPTY", "tables": {}, "total_rows": 0}

    # Deduplicate files by stem (case-insensitive), keeping the most recently updated file
    file_map = {}
    for f in sorted(all_files, key=lambda p: p.stat().st_mtime):
        file_map[f.stem.lower()] = f
    discovered_files = list(file_map.values())

    for file_path in discovered_files:
        table_name = file_path.stem.lower()
        file_ext = file_path.suffix.lower()
        source_type = "CSV" if file_ext == ".csv" else ("JSON" if file_ext == ".json" else ("PARQUET" if file_ext == ".parquet" else "OTHER"))
        start_time = datetime.now()

        try:
            # Read raw source without structural alterations to preserve raw fidelity
            if file_ext == ".csv":
                df = pd.read_csv(file_path, dtype=str)  # read as string to preserve raw format
            elif file_ext == ".json":
                df = pd.read_json(file_path, dtype=False)
                df = df.astype(str)
            elif file_ext == ".parquet":
                df = pd.read_parquet(file_path)
                df = df.astype(str)
            else:
                continue

            rows_read = len(df)

            # Bronze metadata columns
            df["_bronze_ingested_at"] = start_time.isoformat()
            df["_bronze_run_id"] = run_id
            df["_bronze_source_file"] = file_path.name
            df["_bronze_source_format"] = source_type

            # Write Parquet to Bronze directory
            parquet_path = bronze_dir / f"{table_name}.parquet"
            df.to_parquet(parquet_path, index=False)

            # Register as DuckDB table bronze_{table_name}
            duckdb_table_name = f"bronze_{table_name}"
            save_df_to_table(duckdb_table_name, df, overwrite=True)

            rows_written = len(df)
            total_rows += rows_written

            # Record in DuckDB ingestion_runs metadata table
            execute_query(
                """
                INSERT INTO ingestion_runs (
                    run_id, source_file, source_type, ingestion_timestamp,
                    rows_read, rows_written, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    file_path.name,
                    source_type,
                    start_time,
                    rows_read,
                    rows_written,
                    "SUCCESS",
                    "",
                ],
            )

            results[table_name] = {
                "source_file": file_path.name,
                "format": source_type,
                "rows": rows_written,
                "columns": list(df.columns),
                "status": "SUCCESS",
            }
            logger.info(f"Bronze Ingested: {table_name} ({rows_written} rows)")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to ingest {file_path.name}: {err_msg}")
            execute_query(
                """
                INSERT INTO ingestion_runs (
                    run_id, source_file, source_type, ingestion_timestamp,
                    rows_read, rows_written, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    file_path.name,
                    source_type,
                    start_time,
                    0,
                    0,
                    "FAILED",
                    err_msg,
                ],
            )
            results[table_name] = {
                "source_file": file_path.name,
                "format": source_type,
                "rows": 0,
                "status": "FAILED",
                "error": err_msg,
            }

    return {
        "run_id": run_id,
        "status": "SUCCESS" if all(r.get("status") == "SUCCESS" for r in results.values()) else "PARTIAL",
        "tables": results,
        "total_rows": total_rows,
        "ingested_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    ingest_bronze_layer()
