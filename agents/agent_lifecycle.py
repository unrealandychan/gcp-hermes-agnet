"""
agents/agent_lifecycle.py

Runtime agent tree tracking, spawn lifecycle accounting, recursion/delegation
depth limits, and session-level agent count limits.

Closes #15, #16, #17, #18.

──────────────────────────────────────────────────────────────────────────────
Architecture
──────────────────────────────────────────────────────────────────────────────

  AgentLifecycleTracker  — per-session singleton
    ├── spawn(name, parent, task_body)  → reserve slot, record node
    ├── complete(name)                  → release slot, mark done
    ├── fail(name, error)               → release slot, mark failed
    ├── get_tree()                      → current agent tree snapshot
    └── depth_of(name)                 → recursion depth from root

  Limits (all configurable via Settings)
    max_agents_per_session   — total active agents at once (default 20)
    max_delegation_depth     — nesting depth cap (default 5)

  SpawnError  — raised when a limit is exceeded (clear message)

  HTTP exposure
    GET /tasks/{task_id}/agents  →  AgentTreeResponse  (gateway/main.py)

──────────────────────────────────────────────────────────────────────────────
Usage
──────────────────────────────────────────────────────────────────────────────

    from agents.agent_lifecycle import AgentLifecycleTracker

    tracker = AgentLifecycleTracker(session_id="sess-abc")
    tracker.spawn("AnalyticsAgent_0", parent=None, task_body="Fetch revenue")
    tracker.spawn("HRAgent_0", parent=None, task_body="Check policies")
    tracker.complete("AnalyticsAgent_0")
    tree = tracker.get_tree()
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────


class SpawnError(RuntimeError):
    """Raised when an agent cannot be spawned due to a limit violation."""


# ── Default limits ────────────────────────────────────────────────────────────

DEFAULT_MAX_AGENTS_PER_SESSION: int = 20
DEFAULT_MAX_DELEGATION_DEPTH: int = 5


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class AgentNode:
    """A single node in the runtime agent tree."""

    name: str
    parent: Optional[str]           # None = root
    task_body: str
    status: str = "running"         # running | done | failed
    started_at: str = field(default_factory=lambda: _now())
    completed_at: str = ""
    error: str = ""
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "parent": self.parent,
            "task_body": self.task_body,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "children": list(self.children),
        }


# ── Tracker ───────────────────────────────────────────────────────────────────


class AgentLifecycleTracker:
    """
    Tracks the runtime agent tree for a single session.

    Thread-safe — all mutations acquire an internal lock.

    Args:
        session_id:             Opaque session identifier (for logging).
        max_agents_per_session: Hard cap on concurrently *running* agents.
        max_delegation_depth:   Maximum nesting depth (root = depth 0).
    """

    def __init__(
        self,
        session_id: str,
        max_agents_per_session: int = DEFAULT_MAX_AGENTS_PER_SESSION,
        max_delegation_depth: int = DEFAULT_MAX_DELEGATION_DEPTH,
    ) -> None:
        self.session_id = session_id
        self.max_agents = max_agents_per_session
        self.max_depth = max_delegation_depth

        self._lock = threading.Lock()
        self._nodes: dict[str, AgentNode] = {}  # agent_name → node
        self._active_count: int = 0             # currently running agents

    # ── Public API ────────────────────────────────────────────────────────────

    def spawn(
        self,
        name: str,
        parent: str | None = None,
        task_body: str = "",
    ) -> None:
        """
        Reserve a slot and register *name* in the agent tree.

        Raises:
            SpawnError: If ``max_agents_per_session`` or ``max_delegation_depth``
                        would be exceeded.
        """
        with self._lock:
            # ── Limit: session-level agent count (issue #18) ──────────────
            if self._active_count >= self.max_agents:
                raise SpawnError(
                    f"Session '{self.session_id}': cannot spawn '{name}' — "
                    f"max_agents_per_session ({self.max_agents}) reached. "
                    f"Currently active: {self._active_count}."
                )

            # ── Limit: delegation depth (issue #16) ───────────────────────
            depth = self._depth_of_locked(parent)
            if depth >= self.max_depth:
                raise SpawnError(
                    f"Session '{self.session_id}': cannot spawn '{name}' under "
                    f"'{parent}' — max_delegation_depth ({self.max_depth}) exceeded "
                    f"(current depth: {depth})."
                )

            # ── Register node ─────────────────────────────────────────────
            node = AgentNode(name=name, parent=parent, task_body=task_body)
            self._nodes[name] = node

            if parent and parent in self._nodes:
                self._nodes[parent].children.append(name)

            # ── Lifecycle accounting: reserve slot (issue #17) ────────────
            self._active_count += 1

        logger.debug(
            "AgentLifecycle[%s] spawned '%s' (parent=%s, depth=%d, active=%d/%d)",
            self.session_id, name, parent, depth, self._active_count, self.max_agents,
        )

    def complete(self, name: str) -> None:
        """
        Mark *name* as done and release its active slot.

        Safe to call even if *name* was never spawned (no-op with a warning).
        """
        self._finish(name, status="done", error="")

    def fail(self, name: str, error: str = "") -> None:
        """
        Mark *name* as failed and release its active slot.

        Safe to call even if *name* was never spawned (no-op with a warning).
        """
        self._finish(name, status="failed", error=error[:2000])

    def get_tree(self) -> list[dict]:
        """
        Return a snapshot of the full agent tree as a list of node dicts.

        The list is ordered depth-first (parent before children).
        """
        with self._lock:
            roots = [n for n in self._nodes.values() if n.parent is None]
            result: list[dict] = []
            stack = list(roots)
            while stack:
                node = stack.pop(0)
                result.append(node.to_dict())
                for child_name in node.children:
                    child = self._nodes.get(child_name)
                    if child:
                        stack.insert(0, child)
            return result

    def depth_of(self, name: str) -> int:
        """
        Return the nesting depth of *name* (0 = root).

        Returns -1 if *name* is not in the tree.
        """
        with self._lock:
            return self._depth_of_locked(name)

    @property
    def active_count(self) -> int:
        """Number of currently running agents."""
        return self._active_count

    # ── Private helpers ───────────────────────────────────────────────────────

    def _depth_of_locked(self, name: str | None) -> int:
        """
        Compute depth of *name* WITHOUT acquiring the lock (caller holds it).

        Depth is defined as the number of ancestor nodes above *name*:
          root (no parent) → depth 0
          child of root     → depth 1
          grandchild        → depth 2

        Returns -1 if *name* is not in the tree (unknown agent).
        For ``name=None`` (spawn at root level) returns 0.
        """
        if name is None:
            return 0
        node = self._nodes.get(name)
        if node is None:
            return -1
        depth = 0
        current_parent = node.parent
        visited: set[str] = set()
        while current_parent is not None:
            if current_parent in visited:
                logger.warning("Cycle detected in agent tree at '%s'", current_parent)
                break
            visited.add(current_parent)
            parent_node = self._nodes.get(current_parent)
            if parent_node is None:
                break
            current_parent = parent_node.parent
            depth += 1
        return depth

    def _finish(self, name: str, status: str, error: str) -> None:
        with self._lock:
            node = self._nodes.get(name)
            if node is None:
                logger.warning(
                    "AgentLifecycle[%s]: finish called for unknown agent '%s'",
                    self.session_id, name,
                )
                return
            if node.status == "running":
                # ── Lifecycle accounting: release slot (issue #17) ────────
                self._active_count = max(0, self._active_count - 1)
            node.status = status
            node.completed_at = _now()
            node.error = error

        logger.debug(
            "AgentLifecycle[%s] %s '%s' (active=%d/%d)",
            self.session_id, status, name, self._active_count, self.max_agents,
        )


# ── Session registry (one tracker per session) ────────────────────────────────

_registry: dict[str, AgentLifecycleTracker] = {}
_registry_lock = threading.Lock()


def get_tracker(
    session_id: str,
    max_agents_per_session: int = DEFAULT_MAX_AGENTS_PER_SESSION,
    max_delegation_depth: int = DEFAULT_MAX_DELEGATION_DEPTH,
) -> AgentLifecycleTracker:
    """
    Return (or lazily create) the lifecycle tracker for *session_id*.

    Limits are applied only when creating a new tracker — an existing tracker
    retains its original limits.
    """
    with _registry_lock:
        if session_id not in _registry:
            _registry[session_id] = AgentLifecycleTracker(
                session_id=session_id,
                max_agents_per_session=max_agents_per_session,
                max_delegation_depth=max_delegation_depth,
            )
        return _registry[session_id]


def remove_tracker(session_id: str) -> None:
    """Remove the tracker for *session_id* (call when session ends)."""
    with _registry_lock:
        _registry.pop(session_id, None)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
