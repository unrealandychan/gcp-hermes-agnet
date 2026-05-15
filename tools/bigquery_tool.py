"""
tools/bigquery_tool.py

ADK FunctionTool wrapping BigQuery read-only query execution.
The tool accepts a GoogleSQL query string and optional parameters, runs it
against the project's BigQuery instance, and returns rows as a list of dicts.

Security notes:
- Only SELECT queries are permitted (DML/DDL is rejected before execution).
- Query cost is capped via a bytes_billed limit.
- Results are capped at MAX_ROWS to avoid context overload.
"""
import re
from functools import lru_cache
from typing import Any

from google.adk.tools import FunctionTool
from google.cloud import bigquery

from config import Settings


@lru_cache(maxsize=None)
def _get_bq_client(project_id: str) -> bigquery.Client:
    """Return a cached BigQuery client. Created once per project_id per process."""
    return bigquery.Client(project=project_id)

MAX_ROWS = 500
MAX_BYTES_BILLED = 10 * 1024 ** 3  # 10 GB hard cap

_DDL_DML_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|MERGE|TRUNCATE|CALL)\b",
    re.IGNORECASE,
)


def _run_query(project_id: str, query: str, params: dict[str, Any] | None = None) -> dict:
    """
    Execute a read-only BigQuery GoogleSQL query and return up to MAX_ROWS rows.

    Args:
        project_id: GCP project ID.
        query: GoogleSQL SELECT statement.
        params: Optional dict of query parameters {name: value}.

    Returns:
        dict with keys: rows (list[dict]), total_rows (int), schema (list[str]).
        On error, returns {"error": "<message>"}.
    """
    if _DDL_DML_PATTERN.match(query):
        return {"error": "Only SELECT queries are permitted."}

    client = _get_bq_client(project_id)
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES_BILLED,
        use_query_cache=True,
    )
    if params:
        job_config.query_parameters = [
            bigquery.ScalarQueryParameter(k, _infer_bq_type(v), v)
            for k, v in params.items()
        ]

    try:
        job = client.query(query, job_config=job_config)
        result = job.result()
        schema = [field.name for field in result.schema]
        rows = [dict(row) for row in result]
        rows = rows[:MAX_ROWS]
        return {"rows": rows, "total_rows": result.total_rows, "schema": schema}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _infer_bq_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"


def make_bigquery_tool(settings: Settings) -> FunctionTool:
    project_id = settings.gcp_project_id

    def bigquery_query(query: str, params: dict[str, Any] | None = None) -> dict:
        """
        Run a read-only BigQuery SQL query.

        Args:
            query: A GoogleSQL SELECT statement.
            params: Optional dict mapping parameter names to values.

        Returns:
            A dict with 'rows', 'total_rows', 'schema', or 'error' on failure.
        """
        return _run_query(project_id, query, params)

    return FunctionTool(func=bigquery_query)


def run_bigquery_query(query: str, params: dict | None = None) -> dict:
    """
    Module-level BigQuery query function for direct tool use (e.g. TaskAgent).

    Args:
        query: A GoogleSQL SELECT statement.
        params: Optional dict mapping parameter names to values.

    Returns:
        A dict with 'rows', 'total_rows', 'schema', or 'error' on failure.
    """
    from config import get_settings
    return _run_query(get_settings().gcp_project_id, query, params)
