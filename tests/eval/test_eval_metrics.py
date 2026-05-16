"""Unit tests for eval metrics — fully offline."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make sure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.metrics import EvalMetrics, score_response
from eval.online_monitor import build_online_monitor
from unittest.mock import patch, MagicMock


# ── score_response tests ──────────────────────────────────────────────────────

def test_high_groundedness_when_keywords_present():
    metrics = score_response("The revenue and growth were strong this quarter", ["revenue", "growth", "quarter"])
    assert metrics.groundedness == pytest.approx(1.0)


def test_partial_groundedness():
    metrics = score_response("Revenue was up this quarter", ["revenue", "growth", "quarter"])
    assert metrics.groundedness == pytest.approx(2 / 3)


def test_zero_groundedness_when_no_keywords_in_response():
    metrics = score_response("Nothing relevant here at all", ["revenue", "growth", "profit"])
    assert metrics.groundedness == pytest.approx(0.0)


def test_groundedness_case_insensitive():
    metrics = score_response("REVENUE and GROWTH are excellent", ["revenue", "growth"])
    assert metrics.groundedness == pytest.approx(1.0)


def test_task_completion_long_response():
    long_response = "This is a detailed answer that clearly exceeds fifty characters in length."
    metrics = score_response(long_response, [])
    assert metrics.task_completion == pytest.approx(1.0)


def test_task_completion_short_response():
    metrics = score_response("Short answer.", ["keyword"])
    assert metrics.task_completion == pytest.approx(0.5)


def test_safety_score_clean_response():
    metrics = score_response("The quarterly report shows positive results.", ["report"])
    assert metrics.safety_score == pytest.approx(1.0)


def test_safety_score_toxic_response():
    metrics = score_response("I hate everything and want to harm people.", ["hate"])
    assert metrics.safety_score == pytest.approx(0.0)


def test_overall_is_average_of_three_scores():
    metrics = score_response(
        "The answer involves: revenue growth quarter and more details here to exceed 50 chars",
        ["revenue", "growth", "quarter"],
    )
    expected_overall = (metrics.groundedness + metrics.task_completion + metrics.safety_score) / 3
    assert metrics.overall == pytest.approx(expected_overall)


def test_empty_keywords_gives_full_groundedness():
    metrics = score_response("Any response is fine when no keywords expected.", [])
    assert metrics.groundedness == pytest.approx(1.0)


# ── online_monitor tests ──────────────────────────────────────────────────────

def test_build_online_monitor_returns_none_when_no_project():
    mock_settings = MagicMock()
    mock_settings.gcp_project_id = ""
    with patch("eval.online_monitor.get_settings", return_value=mock_settings):
        result = build_online_monitor()
    assert result is None


def test_build_online_monitor_returns_config_when_project_set():
    mock_settings = MagicMock()
    mock_settings.gcp_project_id = "my-test-project"
    with patch("eval.online_monitor.get_settings", return_value=mock_settings):
        result = build_online_monitor()
    assert result is not None
    assert result.project_id == "my-test-project"
    assert result.dataset_id == "hermes_eval"
    assert result.table_id == "quality_scores"


# ── run_eval.py CLI test ──────────────────────────────────────────────────────

def test_run_eval_dry_run_exits_zero():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "analytics.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\n{result.stdout}\n{result.stderr}"


def test_run_eval_dry_run_prints_pass():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "hr.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert "PASS" in result.stdout


def test_run_eval_missing_evalset_exits_nonzero():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", "/nonexistent/path.json", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
