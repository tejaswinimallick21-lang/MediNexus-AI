"""Read-only access to the model registry (metrics stored as JSON at training time)."""

import json
from typing import Any, Dict

from src.utils.database import query_df_strict


def active_metrics(model_name: str) -> Dict[str, Any]:
    df = query_df_strict(
        "SELECT metrics FROM model_registry WHERE model_name = ? AND status = 'ACTIVE' ORDER BY training_timestamp DESC LIMIT 1",
        [model_name],
    )
    if df.empty:
        return {}
    raw = df.iloc[0]["metrics"]
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError):
        return {}
