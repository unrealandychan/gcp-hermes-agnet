"""Unit tests for eval metrics — fully offline.

Covers:
  - score_response() — keyword groundedness, task completion, safety
  - score_tool_trajectory() — precision, recall, F1
  - score_rubric() — offline rubric heuristics
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Make sure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.metrics import (
    EvalMetrics,
    RubricScore,
    ToolTrajectoryScore,
    score_response,
    score_rubric,
    score_tool_trajectory,
)
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


# ── score_tool_trajectory tests ──────────────────────────────────────────────

def test_tool_trajectory_perfect_match():
    score = score_tool_trajectory(["bigquery", "search_knowledge_base"], ["bigquery", "search_knowledge_base"])
    assert score.precision == pytest.approx(1.0)
    assert score.recall == pytest.approx(1.0)
    assert score.f1 == pytest.approx(1.0)


def test_tool_trajectory_partial_match():
    score = score_tool_trajectory(["bigquery", "search_knowledge_base", "storage"], ["bigquery"])
    assert score.recall == pytest.approx(1 / 3)
    assert score.precision == pytest.approx(1.0)
    assert score.f1 < 1.0


def test_tool_trajectory_no_match():
    score = score_tool_trajectory(["bigquery"], ["slack_send"])
    assert score.f1 == pytest.approx(0.0)
    assert score.precision == pytest.approx(0.0)
    assert score.recall == pytest.approx(0.0)


def test_tool_trajectory_empty_expected():
    """No expected tools = perfect score (any tools allowed)."""
    score = score_tool_trajectory([], ["bigquery", "storage"])
    assert score.f1 == pytest.approx(1.0)


def test_tool_trajectory_both_empty():
    score = score_tool_trajectory([], [])
    assert score.f1 == pytest.approx(1.0)


def test_tool_trajectory_agent_transfer():
    expected = ["transfer_to_agent:HRAgent", "transfer_to_agent:ITHelpdeskAgent"]
    actual = ["transfer_to_agent:HRAgent", "transfer_to_agent:ITHelpdeskAgent"]
    score = score_tool_trajectory(expected, actual)
    assert score.f1 == pytest.approx(1.0)


def test_tool_trajectory_partial_agent_transfer():
    expected = ["transfer_to_agent:HRAgent", "transfer_to_agent:ITHelpdeskAgent"]
    actual = ["transfer_to_agent:HRAgent"]
    score = score_tool_trajectory(expected, actual)
    assert score.recall == pytest.approx(0.5)


# ── score_rubric tests ────────────────────────────────────────────────────────

def test_rubric_passes_with_good_response():
    rubric = "Response must include working code example with retry and exception handling."
    response = (
        "Here is a working code example with retry logic and exception handling. "
        "The implementation uses exponential backoff for robustness. "
        "See below for the complete solution with detailed inline comments."
    )
    result = score_rubric(response, rubric, pass_threshold=0.5)
    assert result.passed is True


def test_rubric_fails_short_response():
    rubric = "Response must include code example with retry and exception handling."
    result = score_rubric("Short.", rubric, pass_threshold=0.8)
    assert result.passed is False
    assert "short" in result.reason


def test_rubric_fails_toxic_response():
    rubric = "Response must explain the process clearly."
    result = score_rubric("I hate this and want to harm the system.", rubric, pass_threshold=0.3)
    assert result.passed is False
    assert "safety" in result.reason


def test_rubric_score_is_float_between_0_and_1():
    result = score_rubric("Some response text", "Some rubric criteria for evaluation here.")
    assert 0.0 <= result.score <= 1.0


def test_rubric_empty_rubric():
    """Empty rubric — only length and safety checks apply."""
    result = score_rubric(
        "A fairly long response that should pass the length check easily and covers the basics.",
        rubric="",
    )
    assert isinstance(result, RubricScore)
    assert 0.0 <= result.score <= 1.0


# ── online_monitor tests ──────────────────────────────────────────────────────

def test_build_online_monitor_returns_none_when_no_project():
    mock_settings = MagicMock()
    mock_settings.gcp_project_id = ""
    with patch("eval.online_monitor.get_settings", return_value=mock_settings):
        from eval.online_monitor import build_online_monitor
        result = build_online_monitor()
    assert result is None


def test_build_online_monitor_returns_config_when_project_set():
    mock_settings = MagicMock()
    mock_settings.gcp_project_id = "my-test-project"
    with patch("eval.online_monitor.get_settings", return_value=mock_settings):
        from eval.online_monitor import build_online_monitor
        result = build_online_monitor()
    assert result is not None
    assert result.project_id == "my-test-project"
    assert result.dataset_id == "hermes_eval"
    assert result.table_id == "quality_scores"


# ── run_eval.py CLI tests ─────────────────────────────────────────────────────

def test_run_eval_dry_run_exits_zero():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "analytics.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Expected exit 0\n{result.stdout}\n{result.stderr}"


def test_run_eval_dry_run_prints_pass():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "hr.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert "PASS" in result.stdout


def test_run_eval_developer_evalset():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "developer.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"developer evalset failed\n{result.stdout}\n{result.stderr}"


def test_run_eval_task_agent_evalset():
    evalset = PROJECT_ROOT / "eval" / "evalsets" / "task_agent.evalset.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", str(evalset), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"task_agent evalset failed\n{result.stdout}\n{result.stderr}"


def test_run_eval_all_from_config():
    config = PROJECT_ROOT / "eval" / "eval_config.json"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--config", str(config), "--all", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"all evalsets failed\n{result.stdout}\n{result.stderr}"
    assert "GRAND TOTAL" in result.stdout


def test_run_eval_missing_evalset_exits_nonzero():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py"),
         "--evalset", "/nonexistent/path.json", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_run_eval_no_args_exits_nonzero():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "run_eval.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
