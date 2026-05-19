"""Unit tests for gateway/bq_analytics.py — fully offline (BigQuery mocked)."""
from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gateway.bq_analytics import BQAnalytics, TurnRecord, build_bq_analytics, COMPLETIONS_VIEW_SQL


def _make_bq(project="test-project", dataset="hermes_analytics", table="agent_turns"):
    return BQAnalytics(project_id=project, dataset_id=dataset, table_id=table)


# ── TurnRecord ────────────────────────────────────────────────────────────────

def test_turn_record_to_bq_row_fields():
    rec = TurnRecord(
        user_id="u1", session_id="s1", agent_name="HRAgent",
        prompt="What is PTO?", response="PTO is paid time off.",
        latency_ms=123.4, model="gemini-2.0-flash",
    )
    row = rec.to_bq_row()
    assert row["user_id"] == "u1"
    assert row["session_id"] == "s1"
    assert row["agent_name"] == "HRAgent"
    assert row["prompt"] == "What is PTO?"
    assert row["response"] == "PTO is paid time off."
    assert row["latency_ms"] == pytest.approx(123.4)
    assert row["model"] == "gemini-2.0-flash"
    assert row["eval_score"] is None
    assert "timestamp" in row


def test_turn_record_truncates_long_prompt():
    rec = TurnRecord(
        user_id="u1", session_id="s1", agent_name="A",
        prompt="x" * 5000,
        response="y" * 5000,
    )
    row = rec.to_bq_row()
    assert len(row["prompt"]) == 4096
    assert len(row["response"]) == 4096


def test_turn_record_defaults_timestamp_to_now():
    before = datetime.datetime.now(datetime.timezone.utc)
    rec = TurnRecord(user_id="u", session_id="s", agent_name="A")
    after = datetime.datetime.now(datetime.timezone.utc)
    assert before <= rec.timestamp <= after


def test_turn_record_empty_strings_become_none():
    rec = TurnRecord(user_id="u", session_id="s", agent_name="A", prompt="", model="")
    row = rec.to_bq_row()
    assert row["prompt"] is None
    assert row["model"] is None


# ── BQAnalytics.log_turn ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_turn_calls_insert_rows():
    bq = _make_bq()
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []
    bq._client = mock_client

    await bq.log_turn(user_id="u1", session_id="s1", agent_name="HRAgent",
                      prompt="Hello", response="Hi", latency_ms=50.0)

    mock_client.insert_rows_json.assert_called_once()
    table_ref, rows = mock_client.insert_rows_json.call_args[0]
    assert table_ref == "test-project.hermes_analytics.agent_turns"
    assert len(rows) == 1
    assert rows[0]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_log_turn_swallows_exceptions():
    bq = _make_bq()
    bq._client = MagicMock()
    bq._client.insert_rows_json.side_effect = RuntimeError("BQ down")
    # Should not raise
    await bq.log_turn(user_id="u", session_id="s", agent_name="A")


@pytest.mark.asyncio
async def test_log_turn_logs_insert_errors(caplog):
    bq = _make_bq()
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"errors": [{"message": "quota exceeded"}]}]
    bq._client = mock_client
    import logging
    with caplog.at_level(logging.WARNING, logger="gateway.bq_analytics"):
        await bq.log_turn(user_id="u", session_id="s", agent_name="A", prompt="hi", response="hello")
    assert any("insert errors" in r.message for r in caplog.records)


# ── BQAnalytics.ensure_table ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_table_creates_dataset_and_table():
    bq = _make_bq()
    mock_client = MagicMock()
    mock_client.create_table.return_value = None
    bq._client = mock_client

    with patch("gateway.bq_analytics.BQAnalytics._ensure_table_sync") as mock_sync:
        mock_sync.return_value = None
        await bq.ensure_table()

    mock_sync.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_table_swallows_exceptions():
    bq = _make_bq()
    bq._client = MagicMock()
    bq._client.create_dataset.side_effect = RuntimeError("permissions denied")
    await bq.ensure_table()  # should not raise


# ── completions_view_sql ──────────────────────────────────────────────────────

def test_completions_view_sql_contains_project_and_dataset():
    bq = _make_bq(project="my-project", dataset="my_dataset")
    sql = bq.completions_view_sql()
    assert "my-project" in sql
    assert "my_dataset" in sql
    assert "agent_turns" in sql


def test_completions_view_sql_has_key_columns():
    sql = COMPLETIONS_VIEW_SQL.format(project="p", dataset="d")
    assert "agent_name" in sql
    assert "avg_latency_ms" in sql
    assert "total_prompt_tokens" in sql
    assert "avg_eval_score" in sql


# ── build_bq_analytics ────────────────────────────────────────────────────────

def test_build_bq_analytics_returns_none_when_no_dataset():
    mock_settings = MagicMock()
    mock_settings.bq_analytics_dataset = ""
    mock_settings.gcp_project_id = "p"
    with patch("gateway.bq_analytics.get_settings", return_value=mock_settings):
        from gateway.bq_analytics import build_bq_analytics as _build
        result = _build()
    assert result is None


def test_build_bq_analytics_returns_instance_when_configured():
    mock_settings = MagicMock()
    mock_settings.bq_analytics_dataset = "hermes_analytics"
    mock_settings.bq_analytics_table = "agent_turns"
    mock_settings.gcp_project_id = "gcp-agent-hermes-us"
    with patch("gateway.bq_analytics.get_settings", return_value=mock_settings):
        from gateway.bq_analytics import build_bq_analytics as _build
        result = _build()
    assert result is not None
    assert result._dataset_id == "hermes_analytics"
    assert result._project_id == "gcp-agent-hermes-us"


def test_build_bq_analytics_returns_none_when_no_project():
    mock_settings = MagicMock()
    mock_settings.bq_analytics_dataset = "hermes_analytics"
    mock_settings.gcp_project_id = ""
    with patch("gateway.bq_analytics.get_settings", return_value=mock_settings):
        from gateway.bq_analytics import build_bq_analytics as _build
        result = _build()
    assert result is None
