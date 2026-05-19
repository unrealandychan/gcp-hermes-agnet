"""BigQuery Agent Analytics — gateway/bq_analytics.py

Logs every agent turn (prompt, response, token metadata, latency) to BigQuery
for cross-session query pattern analysis, token usage dashboards, and
LLM-as-judge scoring on production traffic.

Inspired by the agents-cli BigQuery Agent Analytics plugin:
  https://google.github.io/agents-cli/guide/observability/bq-agent-analytics/

Usage:
    # In gateway lifespan (optional — skipped if BQ_ANALYTICS_DATASET not set):
    from gateway.bq_analytics import BQAnalytics, build_bq_analytics
    _bq = build_bq_analytics()

    # After each agent turn (fire-and-forget):
    if _bq:
        asyncio.create_task(_bq.log_turn(
            user_id=user_id,
            session_id=session_id,
            agent_name="Orchestrator",
            prompt=message,
            response=text,
            latency_ms=elapsed_ms,
        ))

Configuration (.env):
    BQ_ANALYTICS_DATASET=hermes_analytics   # BigQuery dataset name
    BQ_ANALYTICS_TABLE=agent_turns          # Table name (auto-created on first write)
    GOOGLE_CLOUD_PROJECT=my-project         # Falls back to gcp_project_id in settings

Schema (auto-created):
    timestamp       TIMESTAMP
    user_id         STRING
    session_id      STRING
    agent_name      STRING
    prompt          STRING
    response        STRING
    prompt_tokens   INTEGER
    response_tokens INTEGER
    latency_ms      FLOAT
    model           STRING
    eval_score      FLOAT   (nullable — set by LLM-as-judge if configured)
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

# BigQuery schema for the agent_turns table
_BQ_SCHEMA = [
    {"name": "timestamp",       "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "user_id",         "type": "STRING",    "mode": "REQUIRED"},
    {"name": "session_id",      "type": "STRING",    "mode": "REQUIRED"},
    {"name": "agent_name",      "type": "STRING",    "mode": "REQUIRED"},
    {"name": "prompt",          "type": "STRING",    "mode": "NULLABLE"},
    {"name": "response",        "type": "STRING",    "mode": "NULLABLE"},
    {"name": "prompt_tokens",   "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "response_tokens", "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "latency_ms",      "type": "FLOAT",     "mode": "NULLABLE"},
    {"name": "model",           "type": "STRING",    "mode": "NULLABLE"},
    {"name": "eval_score",      "type": "FLOAT",     "mode": "NULLABLE"},
]

# SQL view for cross-session analytics (logged in dataset as documentation)
COMPLETIONS_VIEW_SQL = """
-- hermes_analytics.completions_view
-- Cross-session query pattern analysis and token usage dashboard
SELECT
  DATE(timestamp)                                     AS date,
  agent_name,
  COUNT(*)                                            AS total_turns,
  AVG(latency_ms)                                     AS avg_latency_ms,
  SUM(prompt_tokens)                                  AS total_prompt_tokens,
  SUM(response_tokens)                                AS total_response_tokens,
  AVG(eval_score)                                     AS avg_eval_score,
  COUNTIF(eval_score IS NOT NULL)                     AS evaluated_turns,
  COUNTIF(eval_score >= 0.8)                          AS passing_turns
FROM `{project}.{dataset}.agent_turns`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC, total_turns DESC
""".strip()


@dataclass
class TurnRecord:
    """One agent turn to be logged to BigQuery."""
    user_id: str
    session_id: str
    agent_name: str
    prompt: str = ""
    response: str = ""
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    latency_ms: float | None = None
    model: str = ""
    eval_score: float | None = None
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def to_bq_row(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "prompt": self.prompt[:4096] if self.prompt else None,
            "response": self.response[:4096] if self.response else None,
            "prompt_tokens": self.prompt_tokens,
            "response_tokens": self.response_tokens,
            "latency_ms": self.latency_ms,
            "model": self.model or None,
            "eval_score": self.eval_score,
        }


class BQAnalytics:
    """Async BigQuery analytics writer.

    Writes are fire-and-forget (asyncio.to_thread) so they never block the
    hot path. Errors are logged and swallowed — analytics must not impact UX.
    """

    def __init__(
        self,
        project_id: str,
        dataset_id: str,
        table_id: str,
    ) -> None:
        self._project_id = project_id
        self._dataset_id = dataset_id
        self._table_id = table_id
        self._table_ref = f"{project_id}.{dataset_id}.{table_id}"
        self._client: Any = None  # lazy init

    # ── public API ────────────────────────────────────────────────────────────

    async def log_turn(
        self,
        user_id: str,
        session_id: str,
        agent_name: str,
        prompt: str = "",
        response: str = "",
        prompt_tokens: int | None = None,
        response_tokens: int | None = None,
        latency_ms: float | None = None,
        model: str = "",
        eval_score: float | None = None,
    ) -> None:
        """Log a single agent turn to BigQuery (non-blocking)."""
        record = TurnRecord(
            user_id=user_id,
            session_id=session_id,
            agent_name=agent_name,
            prompt=prompt,
            response=response,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            latency_ms=latency_ms,
            model=model,
            eval_score=eval_score,
        )
        try:
            await asyncio.to_thread(self._insert_rows, [record])
        except Exception:  # noqa: BLE001
            logger.exception("BQAnalytics.log_turn failed — analytics skipped")

    async def ensure_table(self) -> None:
        """Create the dataset and table if they don't exist (idempotent)."""
        try:
            await asyncio.to_thread(self._ensure_table_sync)
        except Exception:  # noqa: BLE001
            logger.exception("BQAnalytics.ensure_table failed")

    def completions_view_sql(self) -> str:
        """Return the completions view SQL for this project/dataset."""
        return COMPLETIONS_VIEW_SQL.format(
            project=self._project_id,
            dataset=self._dataset_id,
        )

    # ── private sync helpers (run in thread pool) ─────────────────────────────

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import bigquery  # noqa: PLC0415
            self._client = bigquery.Client(project=self._project_id)
        return self._client

    def _ensure_table_sync(self) -> None:
        from google.cloud import bigquery  # noqa: PLC0415
        from google.api_core.exceptions import Conflict  # noqa: PLC0415

        client = self._get_client()

        # Create dataset if not exists
        dataset_ref = bigquery.DatasetReference(self._project_id, self._dataset_id)
        try:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            client.create_dataset(dataset, exists_ok=True)
            logger.info("BQAnalytics: dataset %s ready", self._dataset_id)
        except Exception:  # noqa: BLE001
            logger.exception("BQAnalytics: failed to create dataset %s", self._dataset_id)
            return

        # Create table if not exists
        table_ref = bigquery.TableReference(dataset_ref, self._table_id)
        schema = [bigquery.SchemaField(**f) for f in _BQ_SCHEMA]  # type: ignore[arg-type]
        table = bigquery.Table(table_ref, schema=schema)
        try:
            client.create_table(table)
            logger.info("BQAnalytics: created table %s", self._table_ref)
        except Conflict:
            logger.debug("BQAnalytics: table %s already exists", self._table_ref)
        except Exception:  # noqa: BLE001
            logger.exception("BQAnalytics: failed to create table %s", self._table_ref)

    def _insert_rows(self, records: list[TurnRecord]) -> None:
        from google.cloud import bigquery  # noqa: PLC0415

        client = self._get_client()
        rows = [r.to_bq_row() for r in records]
        errors = client.insert_rows_json(self._table_ref, rows)
        if errors:
            logger.warning("BQAnalytics: insert errors: %s", errors)
        else:
            logger.debug("BQAnalytics: inserted %d rows to %s", len(rows), self._table_ref)


def build_bq_analytics() -> BQAnalytics | None:
    """Build a BQAnalytics instance from settings, or return None if not configured.

    Returns None when BQ_ANALYTICS_DATASET is not set — callers must check
    for None before calling log_turn().
    """
    settings = get_settings()
    dataset_id: str = getattr(settings, "bq_analytics_dataset", "") or ""
    if not dataset_id:
        return None
    table_id: str = getattr(settings, "bq_analytics_table", "agent_turns") or "agent_turns"
    project_id: str = settings.gcp_project_id
    if not project_id:
        logger.warning("BQAnalytics: gcp_project_id not set — BQ analytics disabled")
        return None
    return BQAnalytics(
        project_id=project_id,
        dataset_id=dataset_id,
        table_id=table_id,
    )
