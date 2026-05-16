"""Online quality monitoring — logs eval metrics to BigQuery asynchronously."""
from __future__ import annotations

import asyncio
import datetime
import os
from config import get_settings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval.metrics import EvalMetrics


@dataclass
class MonitorConfig:
    project_id: str
    dataset_id: str = "hermes_eval"
    table_id: str = "quality_scores"


async def log_quality_score(
    user_id: str,
    agent_name: str,
    query: str,
    response: str,
    metrics: "EvalMetrics",
    config: MonitorConfig | None = None,
) -> None:
    """Async — logs a quality score row to BigQuery. Fails silently."""
    if config is None:
        return

    row = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user_id": user_id,
        "agent_name": agent_name,
        "query": query,
        "response": response,
        "groundedness": metrics.groundedness,
        "task_completion": metrics.task_completion,
        "safety_score": metrics.safety_score,
        "overall": metrics.overall,
    }

    def _insert() -> None:
        try:
            from google.cloud import bigquery  # type: ignore

            client = bigquery.Client(project=config.project_id)
            table_ref = f"{config.project_id}.{config.dataset_id}.{config.table_id}"
            client.insert_rows_json(table_ref, [row])
        except Exception:
            pass  # fail silently

    await asyncio.to_thread(_insert)


def build_online_monitor() -> MonitorConfig | None:
    """Returns a MonitorConfig if GCP_PROJECT_ID is set, else None."""
    try:
        settings = get_settings()
        if not settings.gcp_project_id:
            return None
        return MonitorConfig(project_id=settings.gcp_project_id)
    except Exception:  # noqa: BLE001
        return None
