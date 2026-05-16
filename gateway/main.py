"""
gateway/main.py

Hermes API Gateway — FastAPI application.

Endpoints:
  POST /chat              — SSE streaming chat with the Hermes agent
  GET  /sessions/{user_id} — List active sessions for a user
  DELETE /memories/{user_id} — Clear long-term memory for a user

All endpoints require a valid Google ID token (Bearer).

The gateway connects to the deployed Agent Runtime (Reasoning Engine) via
VertexAiSessionService for session management, and streams events back to the
Web UI using Server-Sent Events (SSE).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import vertexai
from fastapi import FastAPI, HTTPException, Path, Request, status
from fastapi.middleware.cors import CORSMiddleware
from google.adk.runners import Runner
from google.adk.sessions import VertexAiSessionService
from google.genai.types import Content, Part
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from agents import build_adk_app
from config import get_settings
from connectors.slack import router as slack_router
from connectors.teams import router as teams_router
from connectors.telegram import router as telegram_router
from gateway.auth import CurrentUser
from gateway import tasks as task_store
from gateway.observability import agent_span, instrument_fastapi, setup_tracing
from tools.model_armor import screen_prompt
from governance.policy_engine import PolicyEngine, PolicyResult, build_policy_engine

logger = logging.getLogger(__name__)

# ── Rate limiter (per IP) ──────────────────────────────────────────────────────
# 20 chat requests/minute per IP — protects LLM quota & prevents flood abuse.
limiter = Limiter(key_func=get_remote_address)

# ── App lifecycle ──────────────────────────────────────────────────────────────

_runner: Runner | None = None
_policy_engine: PolicyEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner  # noqa: PLW0603
    settings = get_settings()
    settings.inject_litellm_env()  # export provider API keys for LiteLLM

    # ── Agent Observability: Cloud Trace ──────────────────────────────────
    if settings.enable_cloud_trace:
        setup_tracing(project_id=settings.gcp_project_id)
        instrument_fastapi(app)

    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)

    session_service = VertexAiSessionService(
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    app_name = settings.reasoning_engine_resource_name or "hermes-local"
    adk_app = build_adk_app()
    _runner = Runner(
        agent=adk_app.agent,
        app_name=app_name,
        session_service=session_service,
    )
    logger.info("Hermes gateway started. App: %s", app_name)
    global _policy_engine  # noqa: PLW0603
    _policy_engine = build_policy_engine()
    if _policy_engine:
        logger.info("PolicyEngine loaded %d rules.", len(_policy_engine.rules))
    else:
        logger.warning("PolicyEngine unavailable — governance checks disabled.")
    yield
    logger.info("Hermes gateway shutting down.")


# ── FastAPI app ────────────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="Hermes Agent Gateway",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# Attach rate limiter state and 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Platform connectors ────────────────────────────────────────────────────────
app.include_router(telegram_router)
app.include_router(slack_router)
app.include_router(teams_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Request / Response models ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # client may resume an existing session


class ChatEvent(BaseModel):
    type: str  # "text" | "done" | "error"
    content: str = ""
    session_id: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    user: CurrentUser,
) -> EventSourceResponse:
    """
    Stream chat responses as Server-Sent Events.

    Each SSE event is a JSON-encoded ChatEvent.
    Final event has type='done'.
    """
    if not _runner:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent runner not initialised.",
        )

    user_id: str = user.get("sub", "anonymous")

    # ── Model Armor: screen incoming prompt ────────────────────────────────────
    armor = await screen_prompt(body.message)
    if armor.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message blocked by safety policy: {armor.reason}",
        )

    # ── Governance: check prompt against semantic policies ─────────────────────
    if _policy_engine:
        prompt_policy = _policy_engine.check_prompt("Orchestrator", body.message)
        if prompt_policy.action == "block":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request blocked by governance policy: {prompt_policy.reason}",
            )

    # Re-use existing session or create a new one
    session_id = body.session_id
    if not session_id:
        session = await _runner.session_service.create_session(
            app_name=_runner.app_name,
            user_id=user_id,
        )
        session_id = session.id

    return EventSourceResponse(
        _stream_agent(user_id, session_id, body.message),
        media_type="text/event-stream",
    )


async def _stream_agent(
    user_id: str,
    session_id: str,
    message: str,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted JSON strings for each agent event."""
    user_content = Content(role="user", parts=[Part(text=message)])
    with agent_span("Orchestrator", user_id=user_id, session_id=session_id) as span:
        span.set_attribute("hermes.message_len", len(message))
        try:
            async for event in _runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content,
            ):
                if event.is_final_response():
                    text = ""
                    if event.content and event.content.parts:
                        text = "".join(
                            getattr(p, "text", "") for p in event.content.parts
                        )
                    # ── Governance: check response ─────────────────────────────
                    if _policy_engine:
                        resp_policy = _policy_engine.check_response("Orchestrator", text)
                        if resp_policy.action == "block":
                            text = "[Response blocked by governance policy]"
                            logger.warning(
                                "Response blocked by policy %s for user %s",
                                resp_policy.violated_policy_id, user_id,
                            )
                    yield _sse(ChatEvent(type="text", content=text, session_id=session_id))

            yield _sse(ChatEvent(type="done", session_id=session_id))

        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent stream error.")
            yield _sse(ChatEvent(type="error", content=str(exc), session_id=session_id))


def _sse(event: ChatEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


@app.get("/sessions/{user_id}")
async def list_sessions(
    user_id: str = Path(..., min_length=1, max_length=128),
    user: CurrentUser = ...,
) -> dict:
    """List active sessions for the authenticated user."""
    # Only allow users to query their own sessions
    caller_id: str = user.get("sub", "")
    if caller_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot list sessions for another user.",
        )
    if not _runner:
        return {"sessions": []}
    sessions = await _runner.session_service.list_sessions(
        app_name=_runner.app_name, user_id=user_id
    )
    return {"sessions": [{"id": s.id, "create_time": str(s.create_time)} for s in sessions.sessions]}


@app.delete("/memories/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_memories(
    user_id: str = Path(..., min_length=1, max_length=128),
    user: CurrentUser = ...,
) -> None:
    """Clear all long-term memories for the authenticated user."""
    caller_id: str = user.get("sub", "")
    if caller_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot clear memories for another user.",
        )
    # ADK VertexAiMemoryBankService deletion (best-effort; logs on failure)
    try:
        if _runner:
            await _runner.memory_service.delete_memories(  # type: ignore[attr-defined]
                app_name=_runner.app_name, user_id=user_id
            )
    except AttributeError:
        logger.warning("Memory service does not support delete_memories.")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to delete memories for user %s", user_id)


# ── Long-running task endpoints ────────────────────────────────────────────────


class TaskRequest(BaseModel):
    task: str                           # Plain-text description of the task
    context: dict[str, str] | None = None  # Optional structured context


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def submit_task(
    request: Request,
    body: TaskRequest,
    user: CurrentUser,
) -> dict:
    """
    Submit a long-running task to the ReAct LoopAgent.

    Returns immediately with a task_id and status='pending'.
    The task runs in the background for up to 1 hour.

    Poll GET /tasks/{task_id} for status and results.
    """
    user_id: str = user.get("sub", "anonymous")
    record = task_store.submit_task(
        task=body.task,
        user_id=user_id,
        context=body.context,
    )
    return record


@app.get("/tasks/{task_id}")
async def get_task(
    task_id: str = Path(..., min_length=36, max_length=36),
    user: CurrentUser = ...,
) -> dict:
    """
    Poll the status of a long-running task.

    status values:
      pending   — queued, not yet started
      running   — LoopAgent is actively working
      done      — completed successfully; result field contains the answer
      failed    — an error occurred; error field contains the message
      cancelled — client called DELETE /tasks/{task_id}

    progress is a list of intermediate notes from the agent.
    """
    record = task_store.get_task(task_id)
    if record is None:
        # Try GCS for tasks from previous instances
        record = await task_store.load_task_from_gcs(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    caller_id: str = user.get("sub", "")
    if record["user_id"] != caller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    return record


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: str = Path(..., min_length=36, max_length=36),
    user: CurrentUser = ...,
) -> None:
    """Cancel a running task. No-op if the task is already complete."""
    record = task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    caller_id: str = user.get("sub", "")
    if record["user_id"] != caller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    task_store.cancel_task(task_id)


@app.get("/tasks")
async def list_my_tasks(user: CurrentUser) -> dict:
    """List all tasks submitted by the authenticated user (most recent first)."""
    user_id: str = user.get("sub", "anonymous")
    return {"tasks": task_store.list_user_tasks(user_id)}


# ── Cloud Scheduler webhook ────────────────────────────────────────────────────


class SchedulerTriggerRequest(BaseModel):
    task: str
    scheduled_by: str = "agent"
    job_name: str = ""


@app.post("/scheduler/trigger", status_code=status.HTTP_202_ACCEPTED)
async def scheduler_trigger(request: Request, body: SchedulerTriggerRequest) -> dict:
    """
    Webhook called by Cloud Scheduler to trigger an agent task.

    Authentication: Cloud Scheduler attaches an OIDC token issued for the
    Hermes service account.  We verify it matches our expected service account
    to prevent unauthorised task injection.

    This endpoint intentionally does NOT use the normal Google OAuth2 CurrentUser
    dependency — Cloud Scheduler is a server-to-server caller, not a human user.
    """
    # ── Verify OIDC token from Cloud Scheduler ─────────────────────────────────
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token.")

    token = auth_header[len("Bearer "):]
    _verify_scheduler_oidc_token(token)

    # ── Submit task as a system user ───────────────────────────────────────────
    system_user_id = f"scheduler:{body.job_name or 'unknown'}"
    record = task_store.submit_task(
        task=body.task,
        user_id=system_user_id,
        context={"triggered_by": body.scheduled_by, "job_name": body.job_name},
    )
    logger.info("Scheduler triggered task %s: %s", record["task_id"], body.task[:80])
    return {"task_id": record["task_id"], "status": record["status"]}


def _verify_scheduler_oidc_token(token: str) -> None:
    """
    Verify a Google OIDC token and confirm it was issued for our service account.
    Raises HTTPException 401/403 on failure.
    """
    from cachetools import TTLCache  # noqa: PLC0415
    from google.auth.transport import requests as google_requests  # noqa: PLC0415
    from google.oauth2 import id_token  # noqa: PLC0415

    _scheduler_oidc_settings = get_settings()
    expected_sa = _scheduler_oidc_settings.scheduler_service_account
    gateway_url = _scheduler_oidc_settings.gateway_url.rstrip("/")
    audience = f"{gateway_url}/scheduler/trigger"

    try:
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OIDC token: {exc}",
        ) from exc

    if expected_sa and id_info.get("email") != expected_sa:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token service account does not match expected scheduler SA.",
        )
