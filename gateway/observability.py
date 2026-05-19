"""
gateway/observability.py

Agent Observability — OpenTelemetry + Google Cloud Trace.
https://cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview

Provides:
  setup_tracing()      — initialise Cloud Trace exporter at startup
  instrument_fastapi() — auto-instrument all HTTP spans in FastAPI
  get_tracer()         — get a tracer for manual agent-reasoning spans
  agent_span()         — context manager: wrap one agent turn in a span

Environment-aware logging (mirrors agents-cli telemetry.py pattern):
  - LOCAL dev:   spans emitted, but prompt/response content NOT logged (privacy)
  - DEPLOYED:    spans + metadata only (NO_CONTENT mode) — content omitted
  - ENABLE_CLOUD_TRACE=true  — enable tracing (default: true)
  - TRACE_LOG_CONTENT=false  — never log prompt/response text in spans (default: false)

Traces appear in:
  https://console.cloud.google.com/traces?project=<GCP_PROJECT_ID>

Installation (add to requirements.txt — already included):
  opentelemetry-sdk
  opentelemetry-exporter-gcp-trace
  opentelemetry-instrumentation-fastapi

Configuration (.env):
  ENABLE_CLOUD_TRACE=true    # set false to disable (default: true when deployed)
  TRACE_LOG_CONTENT=false    # set true ONLY in local dev to log prompt text
"""
from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-imported; None when opentelemetry packages are not installed.
_tracer: Any = None

# NO_CONTENT mode: when True, prompt/response text is never added to spans.
# Mirrors agents-cli telemetry.py behaviour for deployed environments.
_NO_CONTENT_MODE: bool = not (os.getenv("TRACE_LOG_CONTENT", "false").lower() == "true")


def setup_tracing(project_id: str, service_name: str = "hermes-gateway") -> None:
    """
    Initialise OpenTelemetry with the Google Cloud Trace exporter.

    Safe to call at startup — silently degrades when the packages are
    absent so local development is unaffected.
    """
    global _tracer  # noqa: PLW0603
    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter  # noqa: PLC0415
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

        resource = Resource.create(
            {"service.name": service_name, "gcp.project_id": project_id}
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(CloudTraceSpanExporter(project_id=project_id))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        logger.info("Cloud Trace enabled — project=%s service=%s", project_id, service_name)
    except ImportError:
        logger.info(
            "opentelemetry packages not installed — Cloud Trace disabled. "
            "Run: pip install opentelemetry-sdk opentelemetry-exporter-gcp-trace"
        )


def instrument_fastapi(app: Any) -> None:
    """Auto-instrument a FastAPI app to emit HTTP request/response spans."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI OpenTelemetry auto-instrumentation enabled.")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed — skipping.")


def get_tracer() -> Any:
    """Return the active tracer, or a no-op stub when tracing is disabled."""
    return _tracer or _NoopTracer()


@contextlib.contextmanager
def agent_span(
    agent_name: str,
    user_id: str = "",
    session_id: str = "",
    prompt: str = "",
    response: str = "",
) -> Generator[Any, None, None]:
    """
    Context manager that wraps one agent turn in a Cloud Trace span.

    Follows NO_CONTENT mode by default (agents-cli telemetry.py pattern):
    prompt and response text are only added to spans when TRACE_LOG_CONTENT=true.
    All other metadata (agent name, user_id, session_id) is always logged.

    Usage:
        with agent_span("HRAgent", user_id=uid, session_id=sid,
                        prompt=message, response=text) as span:
            span.set_attribute("hermes.message_len", len(message))

    Falls back to a no-op context manager when tracing is not configured.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"agent/{agent_name}") as span:
        try:
            from opentelemetry.trace import Span  # noqa: PLC0415

            if isinstance(Span, type) and isinstance(span, Span):
                span.set_attribute("hermes.agent", agent_name)
                if user_id:
                    span.set_attribute("hermes.user_id", user_id)
                if session_id:
                    span.set_attribute("hermes.session_id", session_id)
                # NO_CONTENT mode: only log text when explicitly enabled
                if not _NO_CONTENT_MODE:
                    if prompt:
                        span.set_attribute("hermes.prompt", prompt[:512])
                    if response:
                        span.set_attribute("hermes.response", response[:512])
        except ImportError:
            pass
        yield span


# ── No-op fallback ─────────────────────────────────────────────────────────────

class _NoopSpan:
    def set_attribute(self, *_: Any, **__: Any) -> None:
        pass

    def record_exception(self, *_: Any, **__: Any) -> None:
        pass

    def set_status(self, *_: Any, **__: Any) -> None:
        pass


class _NoopTracer:
    @contextlib.contextmanager
    def start_as_current_span(self, _name: str, **__: Any) -> Generator[_NoopSpan, None, None]:
        yield _NoopSpan()
