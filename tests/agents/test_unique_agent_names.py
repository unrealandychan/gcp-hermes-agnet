"""
tests/agents/test_unique_agent_names.py

Tests for unique per-task agent name generation (#13).
"""
from __future__ import annotations

from agents.synthesizer import _unique_suffix, unique_agent_name


def test_suffix_format():
    suffix = _unique_suffix("some task")
    # _<4hex>_<seq>
    parts = suffix.split("_")
    assert len(parts) == 3  # ['', hex, seq]
    assert len(parts[1]) == 4
    assert parts[1].isalnum()
    assert parts[2] == "0"


def test_suffix_deterministic():
    assert _unique_suffix("task A") == _unique_suffix("task A")


def test_suffix_differs_by_task():
    assert _unique_suffix("task A") != _unique_suffix("task B")


def test_suffix_differs_by_seq():
    assert _unique_suffix("task A", seq=0) != _unique_suffix("task A", seq=1)


def test_unique_agent_name_format():
    name = unique_agent_name("AnalyticsAgent", "analyse revenue", seq=0)
    assert name.startswith("AnalyticsAgent_")
    assert name != "AnalyticsAgent"


def test_unique_agent_name_no_collision_across_parallel_copies():
    name0 = unique_agent_name("AnalyticsAgent", "analyse revenue", seq=0)
    name1 = unique_agent_name("AnalyticsAgent", "analyse revenue", seq=1)
    assert name0 != name1


def test_unique_agent_name_stable_for_same_task():
    assert (
        unique_agent_name("HRAgent", "onboard Alice", seq=0)
        == unique_agent_name("HRAgent", "onboard Alice", seq=0)
    )


def test_unique_agent_name_differs_for_different_tasks():
    assert (
        unique_agent_name("HRAgent", "onboard Alice", seq=0)
        != unique_agent_name("HRAgent", "query payroll", seq=0)
    )


def test_unique_agent_name_empty_task_still_suffixes_and_varies_by_seq():
    name0 = unique_agent_name("HRAgent", "", seq=0)
    name1 = unique_agent_name("HRAgent", "", seq=1)
    assert name0.startswith("HRAgent_")
    assert name0 != "HRAgent"
    assert name0 != name1
