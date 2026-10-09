"""
Utilities for data ingestion and quality imperfection injection.
"""

import random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


def inject_realistic_imperfections(
    df: pd.DataFrame,
    date_columns: list = None,
    categorical_columns: list = None,
    nullable_columns: list = None,
    numeric_columns: list = None,
    duplicate_ratio: float = 0.015,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Intentionally inject realistic data quality anomalies into a clean DataFrame.
    Anomalies include:
    - Duplicate rows
    - Missing values (NaN)
    - Inconsistent capitalization
    - Inconsistent date string formats
    - Invalid categorical tokens
    - Occasional invalid numeric anomalies
    """
    random.seed(seed)
    np.random.seed(seed)
    df_imperfect = df.copy()

    n = len(df_imperfect)
    if n == 0:
        return df_imperfect

    # 1. Inject duplicate rows
    if duplicate_ratio > 0:
        num_duplicates = max(1, int(n * duplicate_ratio))
        duplicate_indices = np.random.choice(n, size=num_duplicates, replace=False)
        duplicates = df_imperfect.iloc[duplicate_indices].copy()
        df_imperfect = pd.concat([df_imperfect, duplicates], ignore_index=True)

    # 2. Inconsistent date formats (Sample up to 250 rows for high performance)
    if date_columns:
        for col in date_columns:
            if col in df_imperfect.columns:
                candidates = df_imperfect[col].dropna().index
                if len(candidates) > 0:
                    sample_size = min(250, int(len(candidates) * 0.05) + 5)
                    sample_indices = np.random.choice(candidates, size=sample_size, replace=False)
                    for idx in sample_indices:
                        val = str(df_imperfect.at[idx, col])
                        try:
                            dt = pd.to_datetime(val)
                            choice = random.choice([1, 2, 3])
                            if choice == 1:
                                df_imperfect.at[idx, col] = dt.strftime("%m/%d/%Y")
                            elif choice == 2:
                                df_imperfect.at[idx, col] = dt.strftime("%d-%m-%Y")
                            else:
                                df_imperfect.at[idx, col] = dt.strftime("%Y/%m/%d %H:%M:%S")
                        except Exception:
                            pass

    # 3. Inconsistent capitalization & dirty categorical text
    if categorical_columns:
        for col in categorical_columns:
            if col in df_imperfect.columns:
                candidates = df_imperfect[col].dropna().index
                if len(candidates) > 0:
                    sample_size = min(300, int(len(candidates) * 0.08) + 5)
                    sample_indices = np.random.choice(candidates, size=sample_size, replace=False)
                    for idx in sample_indices:
                        val = str(df_imperfect.at[idx, col])
                        choice = random.choice([1, 2, 3])
                        if choice == 1:
                            df_imperfect.at[idx, col] = val.lower()
                        elif choice == 2:
                            df_imperfect.at[idx, col] = val.upper()
                        else:
                            df_imperfect.at[idx, col] = f"  {val}  "

    # 4. Inject Missing / Null values
    if nullable_columns:
        for col in nullable_columns:
            if col in df_imperfect.columns:
                mask = np.random.rand(len(df_imperfect)) < 0.03
                df_imperfect.loc[mask, col] = None

    # 5. Invalid categorical tokens
    if categorical_columns and len(categorical_columns) > 0:
        target_col = random.choice(categorical_columns)
        if target_col in df_imperfect.columns:
            mask = np.random.rand(len(df_imperfect)) < 0.005
            df_imperfect.loc[mask, target_col] = "UNKNOWN_VAL"

    # 6. Occasional invalid numerical anomalies
    if numeric_columns:
        for col in numeric_columns:
            if col in df_imperfect.columns:
                candidates = df_imperfect[col].dropna().index
                if len(candidates) > 0:
                    sample_size = min(150, int(len(candidates) * 0.005) + 3)
                    sample_indices = np.random.choice(candidates, size=sample_size, replace=False)
                    for idx in sample_indices:
                        val = df_imperfect.at[idx, col]
                        if pd.notna(val) and isinstance(val, (int, float, np.number)):
                            df_imperfect.at[idx, col] = -abs(val)

    return df_imperfect
