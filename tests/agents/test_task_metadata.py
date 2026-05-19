"""
tests/agents/test_task_metadata.py

Unit tests for agents/task_metadata.py — per-agent task assignment store (#14).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from agents.task_metadata import TaskMetadataStore, _in_process


@pytest.fixture(autouse=True)
def clear_in_process():
    """Ensure tests start with a clean in-process store."""
    _in_process.clear()
    yield
    _in_process.clear()


# ── record_assignment ─────────────────────────────────────────────────────────


def test_record_creates_pending_entry():
    store = TaskMetadataStore("task-1")
    store.record_assignment("AnalyticsAgent_abc_0", "Fetch Q3 revenue")
    assignments = store.list_assignments()
    assert len(assignments) == 1
    rec = assignments[0]
    assert rec["agent_name"] == "AnalyticsAgent_abc_0"
    assert rec["task_body"] == "Fetch Q3 revenue"
    assert rec["status"] == "pending"
    assert rec["started_at"] == ""
    assert rec["completed_at"] == ""
    assert rec["error"] == ""


def test_record_multiple_agents():
    store = TaskMetadataStore("task-2")
    store.record_assignment("AgentA_0", "Sub-task A")
    store.record_assignment("AgentB_0", "Sub-task B")
    assert len(store.list_assignments()) == 2


# ── mark_running ──────────────────────────────────────────────────────────────


def test_mark_running_sets_status_and_timestamp():
    store = TaskMetadataStore("task-3")
    store.record_assignment("AgentA_0", "Some task")
    store.mark_running("AgentA_0")
    rec = store.get_assignment("AgentA_0")
    assert rec["status"] == "running"
    assert rec["started_at"] != ""


# ── mark_done ─────────────────────────────────────────────────────────────────


def test_mark_done_sets_completed_status():
    store = TaskMetadataStore("task-4")
    store.record_assignment("AgentA_0", "Some task")
    store.mark_running("AgentA_0")
    store.mark_done("AgentA_0")
    rec = store.get_assignment("AgentA_0")
    assert rec["status"] == "done"
    assert rec["completed_at"] != ""


# ── mark_failed ───────────────────────────────────────────────────────────────


def test_mark_failed_sets_error():
    store = TaskMetadataStore("task-5")
    store.record_assignment("AgentX_0", "Risky task")
    store.mark_failed("AgentX_0", error="Timeout")
    rec = store.get_assignment("AgentX_0")
    assert rec["status"] == "failed"
    assert "Timeout" in rec["error"]
    assert rec["completed_at"] != ""


def test_mark_failed_truncates_long_error():
    store = TaskMetadataStore("task-6")
    store.record_assignment("AgentX_0", "Task")
    store.mark_failed("AgentX_0", error="x" * 5000)
    rec = store.get_assignment("AgentX_0")
    assert len(rec["error"]) <= 2000


# ── get_assignment ────────────────────────────────────────────────────────────


def test_get_assignment_returns_none_for_unknown():
    store = TaskMetadataStore("task-7")
    assert store.get_assignment("NonExistent") is None


# ── Firestore degradation ─────────────────────────────────────────────────────


def test_firestore_failure_does_not_raise():
    """Firestore errors must not propagate — in-process mirror is enough."""
    with patch("agents.task_metadata._get_firestore_client", side_effect=Exception("no creds")):
        store = TaskMetadataStore("task-8")
        store.record_assignment("AgentA_0", "Task body")
        store.mark_running("AgentA_0")
        store.mark_done("AgentA_0")
        rec = store.get_assignment("AgentA_0")
        assert rec["status"] == "done"


# ── task_id isolation ─────────────────────────────────────────────────────────


def test_different_task_ids_are_isolated():
    s1 = TaskMetadataStore("task-A")
    s2 = TaskMetadataStore("task-B")
    s1.record_assignment("Agent_0", "Task for A")
    assert len(s2.list_assignments()) == 0
    assert len(s1.list_assignments()) == 1
