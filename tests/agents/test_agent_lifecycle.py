"""
tests/agents/test_agent_lifecycle.py

Tests for agents/agent_lifecycle.py — covers issues #15, #16, #17, #18.
"""
from __future__ import annotations

import pytest

from agents.agent_lifecycle import (
    DEFAULT_MAX_AGENTS_PER_SESSION,
    DEFAULT_MAX_DELEGATION_DEPTH,
    AgentLifecycleTracker,
    AgentNode,
    SpawnError,
    get_tracker,
    remove_tracker,
    _registry,
)


@pytest.fixture(autouse=True)
def clear_registry():
    _registry.clear()
    yield
    _registry.clear()


# ── Basic spawn / complete / fail ─────────────────────────────────────────────


def test_spawn_registers_node():
    t = AgentLifecycleTracker("sess-1")
    t.spawn("AgentA", parent=None, task_body="Do X")
    tree = t.get_tree()
    assert len(tree) == 1
    assert tree[0]["name"] == "AgentA"
    assert tree[0]["status"] == "running"
    assert tree[0]["task_body"] == "Do X"
    assert tree[0]["parent"] is None


def test_spawn_increments_active_count():
    t = AgentLifecycleTracker("sess-2")
    assert t.active_count == 0
    t.spawn("AgentA")
    assert t.active_count == 1
    t.spawn("AgentB")
    assert t.active_count == 2


def test_complete_decrements_active_count():
    t = AgentLifecycleTracker("sess-3")
    t.spawn("AgentA")
    t.complete("AgentA")
    assert t.active_count == 0


def test_fail_decrements_active_count():
    t = AgentLifecycleTracker("sess-4")
    t.spawn("AgentA")
    t.fail("AgentA", error="timeout")
    assert t.active_count == 0


def test_complete_sets_done_status():
    t = AgentLifecycleTracker("sess-5")
    t.spawn("AgentA")
    t.complete("AgentA")
    node = t.get_tree()[0]
    assert node["status"] == "done"
    assert node["completed_at"] != ""


def test_fail_sets_failed_status_and_error():
    t = AgentLifecycleTracker("sess-6")
    t.spawn("AgentA")
    t.fail("AgentA", error="something broke")
    node = t.get_tree()[0]
    assert node["status"] == "failed"
    assert "something broke" in node["error"]


def test_complete_unknown_agent_is_noop():
    t = AgentLifecycleTracker("sess-7")
    t.complete("NonExistent")  # should not raise


def test_fail_unknown_agent_is_noop():
    t = AgentLifecycleTracker("sess-8")
    t.fail("NonExistent", error="x")  # should not raise


# ── Parent–child tree structure (#15) ────────────────────────────────────────


def test_spawn_child_links_to_parent():
    t = AgentLifecycleTracker("sess-9")
    t.spawn("Parent")
    t.spawn("Child", parent="Parent")
    tree = t.get_tree()
    parent_node = next(n for n in tree if n["name"] == "Parent")
    child_node = next(n for n in tree if n["name"] == "Child")
    assert "Child" in parent_node["children"]
    assert child_node["parent"] == "Parent"


def test_get_tree_depth_first_order():
    t = AgentLifecycleTracker("sess-10")
    t.spawn("Root")
    t.spawn("Child1", parent="Root")
    t.spawn("Child2", parent="Root")
    names = [n["name"] for n in t.get_tree()]
    assert names[0] == "Root"


# ── Depth limit (#16) ────────────────────────────────────────────────────────


def test_depth_limit_raises_spawn_error():
    t = AgentLifecycleTracker("sess-11", max_delegation_depth=2)
    t.spawn("L0")                          # depth 0
    t.spawn("L1", parent="L0")             # depth 1
    t.spawn("L2", parent="L1")             # depth 2 — allowed (2 < max_depth=2 is False... check impl)
    with pytest.raises(SpawnError, match="max_delegation_depth"):
        t.spawn("L3", parent="L2")         # parent at depth 2 >= limit=2 → blocked


def test_depth_within_limit_allowed():
    t = AgentLifecycleTracker("sess-12", max_delegation_depth=3)
    t.spawn("L0")
    t.spawn("L1", parent="L0")
    t.spawn("L2", parent="L1")
    t.spawn("L3", parent="L2")             # parent at depth 2 < 3 → allowed


def test_depth_of_returns_correct_value():
    t = AgentLifecycleTracker("sess-13")
    t.spawn("Root")
    t.spawn("Child", parent="Root")
    t.spawn("GrandChild", parent="Child")
    assert t.depth_of("Root") == 0      # root has no ancestors
    assert t.depth_of("Child") == 1     # 1 ancestor
    assert t.depth_of("GrandChild") == 2  # 2 ancestors


def test_depth_of_unknown_returns_negative_one():
    t = AgentLifecycleTracker("sess-14")
    assert t.depth_of("NonExistent") == -1


# ── Session-level limit (#18) ────────────────────────────────────────────────


def test_session_agent_limit_raises_spawn_error():
    t = AgentLifecycleTracker("sess-15", max_agents_per_session=2)
    t.spawn("A1")
    t.spawn("A2")
    with pytest.raises(SpawnError, match="max_agents_per_session"):
        t.spawn("A3")


def test_session_limit_allows_spawn_after_complete():
    t = AgentLifecycleTracker("sess-16", max_agents_per_session=2)
    t.spawn("A1")
    t.spawn("A2")
    t.complete("A1")
    # slot freed — third spawn should succeed
    t.spawn("A3")
    assert t.active_count == 2


def test_session_limit_allows_spawn_after_fail():
    t = AgentLifecycleTracker("sess-17", max_agents_per_session=1)
    t.spawn("A1")
    t.fail("A1")
    t.spawn("A2")
    assert t.active_count == 1


# ── Lifecycle accounting under concurrency (#17) ─────────────────────────────


def test_active_count_never_goes_negative():
    t = AgentLifecycleTracker("sess-18")
    t.spawn("A")
    t.complete("A")
    t.complete("A")  # double-complete — count must not go below 0
    assert t.active_count == 0


def test_active_count_tracks_running_agents():
    t = AgentLifecycleTracker("sess-19", max_agents_per_session=10)
    for i in range(5):
        t.spawn(f"Agent{i}")
    assert t.active_count == 5
    for i in range(3):
        t.complete(f"Agent{i}")
    assert t.active_count == 2


# ── Session registry ──────────────────────────────────────────────────────────


def test_get_tracker_returns_same_instance():
    t1 = get_tracker("sess-20")
    t2 = get_tracker("sess-20")
    assert t1 is t2


def test_remove_tracker_clears_registry():
    get_tracker("sess-21")
    remove_tracker("sess-21")
    assert "sess-21" not in _registry


def test_get_tracker_creates_new_after_remove():
    t1 = get_tracker("sess-22")
    remove_tracker("sess-22")
    t2 = get_tracker("sess-22")
    assert t1 is not t2


# ── Default constants ─────────────────────────────────────────────────────────


def test_default_max_agents():
    assert DEFAULT_MAX_AGENTS_PER_SESSION == 20


def test_default_max_depth():
    assert DEFAULT_MAX_DELEGATION_DEPTH == 5
