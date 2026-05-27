"""
gateway/tasks.py

Long-running task submission and polling system.

Flow
────
  1. Client sends  POST /tasks  {"task": "...", "context": {...}}
     → Gateway creates a task record in Firestore, fires an asyncio.Task in
       the background, and immediately returns {"task_id": "...", "status": "pending"}.

  2. Background asyncio.Task runs the LoopAgent (up to 1 hour).
     Progress notes are appended as the agent works.

  3. Client polls  GET /tasks/{task_id}  at any interval.
     → Returns status (pending / running / done / failed) + result when done.

  4. Client may cancel with  DELETE /tasks/{task_id}.

Persistence
───────────
  Task records are stored in Firestore (collection: hermes_tasks).
  Firestore is multi-region, strongly consistent, and survives Cloud Run restarts.
  An in-process dict mirrors the record for fast local reads during active runs.

  Firestore document path: hermes_tasks/{task_id}

Timeout
───────
  Each background asyncio.Task is wrapped with asyncio.wait_for(timeout=3600).
  Cloud Run's own timeout is also set to 3600 s (see infra/clouddeploy.yaml).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from google.genai.types import Content, Part

from config import get_settings

logger = logging.getLogger(__name__)

# ── In-process mirror (fast reads for active tasks in this instance) ───────────
_tasks: dict[str, dict] = {}

TASK_TIMEOUT_SECONDS = 3600  # 1 hour hard cap per task
_FIRESTORE_COLLECTION = "hermes_tasks"


# ── Firestore client ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_firestore_client():
    """Return a cached synchronous Firestore client."""
    from google.cloud import firestore  # noqa: PLC0415
    settings = get_settings()
    return firestore.Client(project=settings.gcp_project_id)


def _fs_doc(task_id: str):
    """Return the Firestore DocumentReference for a task."""
    return _get_firestore_client().collection(_FIRESTORE_COLLECTION).document(task_id)


# ── Data helpers ───────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_record(task_id: str, task: str, user_id: str, context: dict) -> dict:
    return {
        "task_id": task_id,
        "user_id": user_id,
        "task": task,
        "context": context,
        "status": "pending",       # pending | running | done | failed | cancelled
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "progress": [],            # list of progress note strings
    }


# ── Firestore persistence ──────────────────────────────────────────────────────


async def _persist(record: dict) -> None:
    """Write/merge the task record to Firestore (non-blocking via thread)."""
    try:
        await asyncio.to_thread(_fs_doc(record["task_id"]).set, record)
    except Exception:  # noqa: BLE001
        logger.warning("Could not persist task %s to Firestore.", record["task_id"])


async def load_task_from_firestore(task_id: str) -> dict | None:
    """Load a task record from Firestore (used after an instance restart)."""
    try:
        snap = await asyncio.to_thread(_fs_doc(task_id).get)
        if snap.exists:
            return snap.to_dict()
    except Exception:  # noqa: BLE001
        pass
    return None


# Keep the old name as an alias so main.py callers don't break
async def load_task_from_gcs(task_id: str) -> dict | None:
    return await load_task_from_firestore(task_id)


# ── Background runner ──────────────────────────────────────────────────────────

# Separate dict for asyncio.Task handles (not serialisable — never written to Firestore)
_asyncio_handles: dict[str, asyncio.Task] = {}


async def _run_task_background(task_id: str) -> None:
    """Background coroutine: runs the LoopAgent for a task."""
    from gateway.main import _runner  # noqa: PLC0415 (lazy import avoids circular)

    record = _tasks.get(task_id)
    if not record:
        return

    record["status"] = "running"
    record["started_at"] = _now_iso()
    await _persist(record)

    if _runner is None:
        record["status"] = "failed"
        record["error"] = "Agent runner not initialised."
        record["completed_at"] = _now_iso()
        await _persist(record)
        return

    # Build a dedicated session for this task
    user_id = record["user_id"]
    session_id = f"task_{task_id}"
    try:
        await _runner.session_service.create_session(
            app_name=_runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:  # noqa: BLE001
        pass  # already exists

    # Compose the initial message: task + any extra context
    import json  # noqa: PLC0415
    context_text = ""
    if record.get("context"):
        context_text = "\n\nAdditional context:\n" + json.dumps(record["context"], indent=2)
    initial_message = f"Task: {record['task']}{context_text}"

    user_content = Content(role="user", parts=[Part(text=initial_message)])

    # ── Use TaskAgent if available; fall back to Orchestrator ──────────────────
    try:
        from agents.task_agent import build_task_agent  # noqa: PLC0415
        from config import get_settings as _gs  # noqa: PLC0415
        from google.adk.runners import Runner  # noqa: PLC0415
        # ADK 2.0: build_task_agent now accepts specialist_agents=None (defaults to fresh copies)
        task_runner = Runner(
            agent=build_task_agent(_gs()),
            app_name=_runner.app_name,
            session_service=_runner.session_service,
        )
    except Exception:  # noqa: BLE001
        logger.warning("TaskAgent unavailable — falling back to Orchestrator.")
        task_runner = _runner

    result_parts: list[str] = []

    async def _do_run() -> None:
        async for event in task_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            if not event.is_final_response() and event.content:
                for part in event.content.parts:
                    text = getattr(part, "text", None)
                    if text and len(text) > 10:
                        record["progress"].append(text[:500])

            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    text = getattr(part, "text", None)
                    if text:
                        result_parts.append(text)

    try:
        await asyncio.wait_for(_do_run(), timeout=TASK_TIMEOUT_SECONDS)
        record["status"] = "done"
        record["result"] = "".join(result_parts) or "Task completed."
    except asyncio.TimeoutError:
        record["status"] = "failed"
        record["error"] = "Task timed out after 1 hour."
        record["result"] = "".join(result_parts) or None
    except asyncio.CancelledError:
        record["status"] = "cancelled"
        record["result"] = "".join(result_parts) or None
        raise  # ADK 2.0: re-raise CancelledError so the framework can handle it
    except Exception as exc:  # noqa: BLE001
        # ADK 2.0: Never catch BaseException here — NodeInterruptedError must propagate
        logger.exception("Task %s failed.", task_id)
        record["status"] = "failed"
        record["error"] = str(exc)
    finally:
        record["completed_at"] = _now_iso()
        _asyncio_handles.pop(task_id, None)
        await _persist(record)


# ── Public API ─────────────────────────────────────────────────────────────────


def _public_record(record: dict) -> dict:
    """Strip internal-only fields before returning to the client."""
    return {k: v for k, v in record.items() if k != "asyncio_task"}


def submit_task(task: str, user_id: str, context: dict | None = None) -> dict:
    """
    Submit a long-running task.  Returns the task record (status=pending).
    The background runner is started as a fire-and-forget asyncio.Task.
    """
    task_id = str(uuid.uuid4())
    record = _make_record(task_id, task, user_id, context or {})
    _tasks[task_id] = record

    bg = asyncio.create_task(_run_task_background(task_id), name=f"task-{task_id}")
    _asyncio_handles[task_id] = bg
    return _public_record(record)


def get_task(task_id: str) -> dict | None:
    """Return the public (serialisable) task record, or None if not found."""
    record = _tasks.get(task_id)
    if record is None:
        return None
    return _public_record(record)


def cancel_task(task_id: str) -> bool:
    """Cancel a running task. Returns True if a cancellation was requested."""
    record = _tasks.get(task_id)
    if not record:
        return False
    bg = _asyncio_handles.get(task_id)
    if bg and not bg.done():
        bg.cancel()
        return True
    return False


def list_user_tasks(user_id: str) -> list[dict]:
    """Return all task records for a given user (most recent first)."""
    records = [r for r in _tasks.values() if r["user_id"] == user_id]
    records.sort(key=lambda r: r["created_at"], reverse=True)
    return [_public_record(r) for r in records]
