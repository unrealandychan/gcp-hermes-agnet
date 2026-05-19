"""
agents/task_metadata.py

Per-agent task assignment metadata store.

Persists the exact task slice delegated to each synthesised agent, along with
timing and status information.  This enables post-mortem debugging and audit
queries on what each agent was asked to do and how long it took.

Schema (stored as a Firestore sub-collection or in-process dict for offline use)
──────────────────────────────────────────────────────────────────────────────────
  Collection: hermes_tasks/{task_id}/agent_assignments/{agent_name}
  Fields:
    agent_name    str   — name of the synthesised agent
    task_id       str   — parent task ID
    task_body     str   — the sub-task text sent to this agent
    status        str   — pending | running | done | failed
    started_at    str   — ISO-8601 UTC timestamp (set when agent starts)
    completed_at  str   — ISO-8601 UTC timestamp (set on done/failed)
    error         str   — error message if status=failed (empty otherwise)

Usage
─────
    from agents.task_metadata import TaskMetadataStore

    store = TaskMetadataStore(task_id="abc123")
    store.record_assignment("AnalyticsAgent_a1b2_0", "Fetch Q3 revenue")
    store.mark_running("AnalyticsAgent_a1b2_0")
    store.mark_done("AnalyticsAgent_a1b2_0")
    assignments = store.list_assignments()
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache

logger = logging.getLogger(__name__)

_PARENT_COLLECTION = "hermes_tasks"
_SUB_COLLECTION = "agent_assignments"


# ── Firestore helper (lazy import) ────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_firestore_client():
    from google.cloud import firestore  # noqa: PLC0415
    from config import get_settings  # noqa: PLC0415
    return firestore.Client(project=get_settings().gcp_project_id)


# ── In-process fallback (used when Firestore is unavailable) ──────────────────

_in_process: dict[str, dict[str, dict]] = {}  # {task_id: {agent_name: record}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────────


class TaskMetadataStore:
    """
    Thread-safe metadata store for per-agent task assignments.

    Falls back gracefully to in-process dict if Firestore is unavailable
    (e.g. local dev without GCP credentials).
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        # Ensure in-process bucket exists
        if task_id not in _in_process:
            _in_process[task_id] = {}

    # ── Write operations ──────────────────────────────────────────────────────

    def record_assignment(self, agent_name: str, task_body: str) -> None:
        """
        Persist a new assignment record for *agent_name*.

        Call this immediately after synthesising the agent, before it starts.
        """
        record = {
            "agent_name": agent_name,
            "task_id": self.task_id,
            "task_body": task_body,
            "status": "pending",
            "started_at": "",
            "completed_at": "",
            "error": "",
        }
        _in_process[self.task_id][agent_name] = record
        self._fs_set(agent_name, record)

    def mark_running(self, agent_name: str) -> None:
        """Mark the assignment as running and record start time."""
        self._update(agent_name, {"status": "running", "started_at": _now()})

    def mark_done(self, agent_name: str) -> None:
        """Mark the assignment as successfully completed."""
        self._update(agent_name, {"status": "done", "completed_at": _now()})

    def mark_failed(self, agent_name: str, error: str = "") -> None:
        """Mark the assignment as failed and record the error message."""
        self._update(
            agent_name,
            {"status": "failed", "completed_at": _now(), "error": error[:2000]},
        )

    # ── Read operations ───────────────────────────────────────────────────────

    def list_assignments(self) -> list[dict]:
        """
        Return all assignment records for this task.

        Reads from the in-process mirror first (fast); falls back to Firestore
        when the mirror is empty (e.g. after a Cloud Run restart).
        """
        local = list(_in_process.get(self.task_id, {}).values())
        if local:
            return local
        return self._fs_list()

    def get_assignment(self, agent_name: str) -> dict | None:
        """Return the assignment record for a specific agent, or None."""
        local = _in_process.get(self.task_id, {}).get(agent_name)
        if local:
            return local
        return self._fs_get(agent_name)

    # ── Firestore I/O (best-effort, never raises) ─────────────────────────────

    def _fs_ref(self, agent_name: str):
        try:
            return (
                _get_firestore_client()
                .collection(_PARENT_COLLECTION)
                .document(self.task_id)
                .collection(_SUB_COLLECTION)
                .document(agent_name)
            )
        except Exception:  # noqa: BLE001
            return None

    def _fs_set(self, agent_name: str, record: dict) -> None:
        ref = self._fs_ref(agent_name)
        if ref is None:
            return
        try:
            ref.set(record)
        except Exception:  # noqa: BLE001
            logger.debug("Firestore set failed for %s/%s — in-process only", self.task_id, agent_name)

    def _fs_update(self, agent_name: str, fields: dict) -> None:
        ref = self._fs_ref(agent_name)
        if ref is None:
            return
        try:
            ref.update(fields)
        except Exception:  # noqa: BLE001
            logger.debug("Firestore update failed for %s/%s", self.task_id, agent_name)

    def _fs_get(self, agent_name: str) -> dict | None:
        ref = self._fs_ref(agent_name)
        if ref is None:
            return None
        try:
            doc = ref.get()
            return doc.to_dict() if doc.exists else None
        except Exception:  # noqa: BLE001
            return None

    def _fs_list(self) -> list[dict]:
        try:
            parent_ref = (
                _get_firestore_client()
                .collection(_PARENT_COLLECTION)
                .document(self.task_id)
                .collection(_SUB_COLLECTION)
            )
            return [doc.to_dict() for doc in parent_ref.stream()]
        except Exception:  # noqa: BLE001
            return []

    def _update(self, agent_name: str, fields: dict) -> None:
        """Apply *fields* to both in-process mirror and Firestore."""
        local = _in_process.setdefault(self.task_id, {}).get(agent_name)
        if local is not None:
            local.update(fields)
        self._fs_update(agent_name, fields)
