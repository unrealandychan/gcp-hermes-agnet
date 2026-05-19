"""Unit tests for eval/optimize.py — fully offline (dry-run mode)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.optimize import (
    InstructionOptimizer,
    OptimizationResult,
    _generate_candidates_dry_run,
    _score_instruction_on_evalset,
)


EVALSET_PATH = PROJECT_ROOT / "eval" / "evalsets" / "hr.evalset.json"
DEV_EVALSET_PATH = PROJECT_ROOT / "eval" / "evalsets" / "developer.evalset.json"


# ── _generate_candidates_dry_run ─────────────────────────────────────────────

def test_dry_run_candidates_returns_n_items():
    candidates = _generate_candidates_dry_run("Base instruction.", [], n=3)
    assert len(candidates) == 3


def test_dry_run_candidates_extend_base_instruction():
    base = "You are an HR agent."
    candidates = _generate_candidates_dry_run(base, [], n=5)
    for c in candidates:
        assert c.startswith(base)


def test_dry_run_candidates_are_distinct():
    candidates = _generate_candidates_dry_run("Base.", [], n=5)
    assert len(set(candidates)) == 5


# ── _score_instruction_on_evalset ─────────────────────────────────────────────

def test_score_evalset_returns_float_in_range():
    cases = json.loads(EVALSET_PATH.read_text())
    avg, results = _score_instruction_on_evalset(cases, dry_run=True)
    assert 0.0 <= avg <= 1.0
    assert len(results) == len(cases)


def test_score_evalset_results_have_required_fields():
    cases = json.loads(EVALSET_PATH.read_text())
    _, results = _score_instruction_on_evalset(cases, dry_run=True)
    for r in results:
        assert "query" in r
        assert "overall" in r
        assert "passed" in r


def test_score_evalset_dry_run_passes_all():
    """Dry-run stubs are designed to hit all keywords → should score well."""
    cases = json.loads(EVALSET_PATH.read_text())
    avg, _ = _score_instruction_on_evalset(cases, dry_run=True)
    # Dry-run uses stubs that include all expected keywords → should be reasonable
    assert avg > 0.4


# ── InstructionOptimizer ─────────────────────────────────────────────────────

def test_optimizer_run_dry_run_returns_result():
    opt = InstructionOptimizer(
        agent_name="HRAgent",
        evalset_path=EVALSET_PATH,
    )
    result = opt.run(max_rounds=2, dry_run=True)
    assert isinstance(result, OptimizationResult)
    assert result.agent_name == "HRAgent"
    assert 0.0 <= result.baseline_score <= 1.0
    assert 0.0 <= result.best_score <= 1.0


def test_optimizer_run_history_has_round_zero():
    opt = InstructionOptimizer(agent_name="HRAgent", evalset_path=EVALSET_PATH)
    result = opt.run(max_rounds=1, dry_run=True)
    assert result.history[0]["round"] == 0
    assert result.history[0]["score"] == pytest.approx(result.baseline_score)


def test_optimizer_run_best_score_ge_baseline():
    opt = InstructionOptimizer(agent_name="DeveloperAgent", evalset_path=DEV_EVALSET_PATH)
    result = opt.run(max_rounds=2, dry_run=True)
    assert result.best_score >= result.baseline_score


def test_optimizer_run_does_not_write_yaml_in_dry_run(tmp_path):
    """write_best=True + dry_run=True should NOT modify agents.yaml."""
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text("agents:\n- name: HRAgent\n  instruction: 'Original instruction'\n")
    opt = InstructionOptimizer(
        agent_name="HRAgent",
        evalset_path=EVALSET_PATH,
        agents_yaml=agents_yaml,
    )
    result = opt.run(max_rounds=1, dry_run=True, write_best=True)
    # dry_run=True means no write even if write_best=True
    content = agents_yaml.read_text()
    assert "Original instruction" in content


def test_optimizer_reads_instruction_from_agents_yaml(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text("agents:\n- name: HRAgent\n  instruction: 'Custom HR instruction'\n")
    opt = InstructionOptimizer(
        agent_name="HRAgent",
        evalset_path=EVALSET_PATH,
        agents_yaml=agents_yaml,
    )
    instruction = opt._read_current_instruction()
    assert instruction == "Custom HR instruction"


def test_optimizer_returns_fallback_instruction_when_agent_not_found(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text("agents:\n- name: AnalyticsAgent\n  instruction: 'Analytics'\n")
    opt = InstructionOptimizer(
        agent_name="HRAgent",
        evalset_path=EVALSET_PATH,
        agents_yaml=agents_yaml,
    )
    instruction = opt._read_current_instruction()
    assert "HRAgent" in instruction


# ── CLI tests ─────────────────────────────────────────────────────────────────

def test_optimize_cli_dry_run_exits_zero():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "optimize.py"),
         "--agent", "HRAgent",
         "--evalset", str(EVALSET_PATH),
         "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Expected exit 0\n{result.stdout}\n{result.stderr}"


def test_optimize_cli_prints_result_summary():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "optimize.py"),
         "--agent", "HRAgent",
         "--evalset", str(EVALSET_PATH),
         "--dry-run", "--rounds", "1"],
        capture_output=True, text=True,
    )
    assert "Baseline" in result.stdout or "Optimizing" in result.stdout


def test_optimize_cli_missing_evalset_exits_nonzero():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "optimize.py"),
         "--agent", "HRAgent",
         "--evalset", "/nonexistent.json",
         "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_optimize_cli_output_json(tmp_path):
    out = tmp_path / "result.json"
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "eval" / "optimize.py"),
         "--agent", "HRAgent",
         "--evalset", str(EVALSET_PATH),
         "--dry-run", "--output", str(out)],
        capture_output=True, text=True,
    )
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["agent_name"] == "HRAgent"
    assert "baseline_score" in data
    assert "best_score" in data
    assert "history" in data
