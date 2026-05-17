"""
tests/conftest.py

Shared pytest configuration and stubs.

All heavy GCP / ADK / Vertex AI packages are pre-stubbed in sys.modules
so the project's source modules can be imported without any GCP
credentials or installed cloud packages.  Tests that need specific
behaviour from these stubs override them with unittest.mock locally.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

# ── Make sure project root is importable ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _make_module(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ── Fake LlmAgent that preserves keyword arguments ─────────────────────────────
class _FakeLlmAgent:
    """Lightweight stand-in for google.adk.agents.LlmAgent."""
    def __init__(self, *, name="", description="", tools=None, sub_agents=None, **_kw):
        self.name = name
        self.description = description
        self.tools = list(tools or [])
        self.sub_agents = list(sub_agents or [])


class _FakeLoopAgent:
    def __init__(self, *, name="", **_kw):
        self.name = name


class _FakeParallelAgent:
    """Lightweight stand-in for google.adk.agents.ParallelAgent."""
    def __init__(self, *, name="", description="", sub_agents=None, **_kw):
        self.name = name
        self.description = description
        self.sub_agents = list(sub_agents or [])


class _FakeSequentialAgent:
    """Lightweight stand-in for google.adk.agents.SequentialAgent."""
    def __init__(self, *, name="", description="", sub_agents=None, **_kw):
        self.name = name
        self.description = description
        self.sub_agents = list(sub_agents or [])


# ── google.auth ────────────────────────────────────────────────────────────────
_google_auth = _make_module("google.auth", default=MagicMock())
_google_auth_transport = _make_module("google.auth.transport")
_google_auth_transport_requests = _make_module(
    "google.auth.transport.requests", Request=MagicMock()
)

# ── google.adk ────────────────────────────────────────────────────────────────
_adk_agents = _make_module(
    "google.adk.agents",
    LlmAgent=_FakeLlmAgent,
    LoopAgent=_FakeLoopAgent,
    ParallelAgent=_FakeParallelAgent,
    SequentialAgent=_FakeSequentialAgent,
)
_adk_tools = _make_module(
    "google.adk.tools",
    FunctionTool=MagicMock(),
    google_search=MagicMock(name="google_search"),
)
_adk_tools_preload = _make_module(
    "google.adk.tools.preload_memory_tool",
    PreloadMemoryTool=MagicMock(),
)
_adk_tools_mcp = _make_module(
    "google.adk.tools.mcp_tool",
    MCPToolset=MagicMock(),
    StdioServerParameters=MagicMock(),
    SseServerParams=MagicMock(),
)
_adk_tools_code = _make_module(
    "google.adk.tools.built_in_code_execution_tool",
    BuiltInCodeExecutionTool=MagicMock(),
)
_adk_runners = _make_module("google.adk.runners", Runner=MagicMock())
_adk_sessions = _make_module("google.adk.sessions", VertexAiSessionService=MagicMock())
_adk_memory = _make_module("google.adk.memory")

# ── google.genai ───────────────────────────────────────────────────────────────
_genai_types = _make_module("google.genai.types", Content=MagicMock(), Part=MagicMock())

# ── vertexai ──────────────────────────────────────────────────────────────────
_vertexai_placeholder = None  # replaced below after Client mock is set up
_vertexai__path_placeholder = []  # __path__ set on real _vertexai below
_vertexai_preview = _make_module("vertexai.preview")
_vertexai_preview.__path__ = []
_vertexai_preview_rag = _make_module(
    "vertexai.preview.rag",
    RagCorpus=MagicMock(),
    RagFile=MagicMock(),
    create_corpus=MagicMock(),
    upload_file=MagicMock(),
    retrieval_query=MagicMock(),
)
_vertexai_agent_engines = _make_module(
    "vertexai.agent_engines",
    create=MagicMock(),
    AdkApp=MagicMock(),
)

# ── vertexai.Client (new SDK >= 1.112 memory API) ─────────────────────────────
_mock_memories = MagicMock()
_mock_memories.generate = MagicMock()
_mock_memories.ingest_events = MagicMock()
_mock_memories.retrieve = MagicMock(return_value=iter([]))
_mock_memories.list = MagicMock(return_value=iter([]))
_mock_memories.create = MagicMock()
_mock_memories.update = MagicMock()
_mock_memories.delete = MagicMock()
_mock_memories.purge = MagicMock()
_mock_agent_engines_ns = MagicMock()
_mock_agent_engines_ns.memories = _mock_memories
_mock_agent_engines_ns.list = MagicMock(return_value=iter([]))
_mock_agent_engines_ns.create = MagicMock()
_mock_vertexai_client_instance = MagicMock()
_mock_vertexai_client_instance.agent_engines = _mock_agent_engines_ns
_MockVertexaiClient = MagicMock(return_value=_mock_vertexai_client_instance)
_vertexai = _make_module("vertexai", init=MagicMock(), Client=_MockVertexaiClient)
_vertexai.__path__ = []  # make it look like a package
_vertexai_preview_reasoning = _make_module(
    "vertexai.preview.reasoning_engines",
    AdkApp=MagicMock(),
)

# ── google.cloud ───────────────────────────────────────────────────────────────
_google_cloud = _make_module("google.cloud")
_google_cloud_bigquery = _make_module("google.cloud.bigquery", Client=MagicMock())
_google_cloud_storage = _make_module("google.cloud.storage", Client=MagicMock())
_google_cloud_firestore = _make_module("google.cloud.firestore", AsyncClient=MagicMock())
_google_cloud_scheduler = _make_module("google.cloud.scheduler_v1", CloudSchedulerClient=MagicMock())

# ── opentelemetry (optional — tests for observability mock these selectively) ──
_otel = _make_module("opentelemetry")
_otel_trace = _make_module("opentelemetry.trace", Span=MagicMock(), get_tracer=MagicMock())
_otel_sdk_trace = _make_module("opentelemetry.sdk.trace", TracerProvider=MagicMock())
_otel_sdk_export = _make_module("opentelemetry.sdk.trace.export", BatchSpanProcessor=MagicMock())
_otel_sdk_res = _make_module("opentelemetry.sdk.resources", Resource=MagicMock())
_otel_exporter = _make_module("opentelemetry.exporter.cloud_trace", CloudTraceSpanExporter=MagicMock())
_otel_fastapi = _make_module(
    "opentelemetry.instrumentation.fastapi", FastAPIInstrumentor=MagicMock()
)

# ── Misc gateway deps ──────────────────────────────────────────────────────────
# slowapi's Limiter.limit must be a pass-through decorator so that FastAPI
# can still inspect the original handler's signature (otherwise → 422).
import functools as _functools


def _noop_limit(_rate: str):
    def _decorator(func):
        @_functools.wraps(func)
        async def _wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return _wrapper
    return _decorator


_LimiterClass = MagicMock()
_LimiterClass.return_value.limit = _noop_limit

_slowapi = _make_module("slowapi", Limiter=_LimiterClass, _rate_limit_exceeded_handler=MagicMock())
_slowapi_errors = _make_module("slowapi.errors", RateLimitExceeded=Exception)
_slowapi_util = _make_module("slowapi.util", get_remote_address=MagicMock())
from starlette.responses import Response as _StarletteResponse


class _FakeEventSourceResponse(_StarletteResponse):
    """Minimal stub so FastAPI accepts EventSourceResponse as a response type."""
    def __init__(self, content=None, *args, **kwargs):
        super().__init__(content="" if content is None else "", media_type="text/event-stream")


_sse_starlette = _make_module("sse_starlette.sse", EventSourceResponse=_FakeEventSourceResponse)

# ── Connector deps ─────────────────────────────────────────────────────────────
_telegram = _make_module("telegram", Bot=MagicMock())
_telegram_ext = _make_module("telegram.ext")
_slack_sdk = _make_module("slack_sdk", WebClient=MagicMock())
_slack_sdk.errors = None  # placeholder
_slack_sdk_web = _make_module("slack_sdk.web")
_slack_sdk_web.__path__ = []
_slack_sdk_web_async = _make_module("slack_sdk.web.async_client", AsyncWebClient=MagicMock())
_slack_sdk_errors = _make_module("slack_sdk.errors", SlackApiError=Exception)
_botframework = _make_module("botframework.core", BotFrameworkAdapter=MagicMock(), BotFrameworkAdapterSettings=MagicMock())
_botframework_schema = _make_module("botframework.schema", Activity=MagicMock())

# ── google.oauth2 ──────────────────────────────────────────────────────────────
_google_oauth2_idtoken = _make_module("google.oauth2.id_token", verify_oauth2_token=MagicMock())
_google_oauth2_credentials = _make_module("google.oauth2.credentials")

# ── jose (JWT) ─────────────────────────────────────────────────────────────────
_jose = _make_module("jose", jwt=MagicMock(), JWTError=Exception, jwk=MagicMock())
_jose_jwt = _make_module("jose.jwt")
_jose_jwk = _make_module("jose.jwk")

# ── google (root namespace) ────────────────────────────────────────────────────
_google = sys.modules.get("google") or _make_module("google")
_google_adk = _make_module("google.adk")
_google_genai = _make_module("google.genai")
_google_oauth2 = _make_module("google.oauth2")


def _register_all():
    mods = {
        "google": _google,
        "google.auth": _google_auth,
        "google.auth.transport": _google_auth_transport,
        "google.auth.transport.requests": _google_auth_transport_requests,
        "google.adk": _google_adk,
        "google.adk.agents": _adk_agents,
        "google.adk.tools": _adk_tools,
        "google.adk.tools.preload_memory_tool": _adk_tools_preload,
        "google.adk.tools.mcp_tool": _adk_tools_mcp,
        "google.adk.tools.built_in_code_execution_tool": _adk_tools_code,
        "google.adk.runners": _adk_runners,
        "google.adk.sessions": _adk_sessions,
        "google.adk.memory": _adk_memory,
        "google.adk.models": _make_module("google.adk.models", LiteLlm=MagicMock()),
        "google.adk.models.lite_llm": _make_module("google.adk.models.lite_llm", LiteLlm=MagicMock()),
        "google.genai": _google_genai,
        "google.genai.types": _genai_types,
        "google.cloud": _google_cloud,
        "google.cloud.bigquery": _google_cloud_bigquery,
        "google.cloud.storage": _google_cloud_storage,
        "google.cloud.firestore": _google_cloud_firestore,
        "google.cloud.scheduler_v1": _google_cloud_scheduler,
        "google.oauth2": _google_oauth2,
        "google.oauth2.id_token": _google_oauth2_idtoken,
        "google.oauth2.credentials": _google_oauth2_credentials,
        "vertexai": _vertexai,
        "vertexai.preview": _vertexai_preview,
        "vertexai.preview.rag": _vertexai_preview_rag,
        "vertexai.agent_engines": _vertexai_agent_engines,
        "vertexai.preview.reasoning_engines": _vertexai_preview_reasoning,
        "opentelemetry": _otel,
        "opentelemetry.trace": _otel_trace,
        "opentelemetry.sdk": _make_module("opentelemetry.sdk"),
        "opentelemetry.sdk.trace": _otel_sdk_trace,
        "opentelemetry.sdk.trace.export": _otel_sdk_export,
        "opentelemetry.sdk.resources": _otel_sdk_res,
        "opentelemetry.exporter": _make_module("opentelemetry.exporter"),
        "opentelemetry.exporter.cloud_trace": _otel_exporter,
        "opentelemetry.instrumentation": _make_module("opentelemetry.instrumentation"),
        "opentelemetry.instrumentation.fastapi": _otel_fastapi,
        "slowapi": _slowapi,
        "slowapi.errors": _slowapi_errors,
        "slowapi.util": _slowapi_util,
        "sse_starlette": _make_module("sse_starlette"),
        "sse_starlette.sse": _sse_starlette,
        "telegram": _telegram,
        "telegram.ext": _telegram_ext,
        "slack_sdk": _slack_sdk,
        "slack_sdk.web": _slack_sdk_web,
        "slack_sdk.web.async_client": _slack_sdk_web_async,
        "slack_sdk.errors": _slack_sdk_errors,
        "botframework": _make_module("botframework"),
        "botframework.core": _botframework,
        "botframework.schema": _botframework_schema,
        "jose": _jose,
        "jose.jwt": _jose_jwt,
        "jose.jwk": _jose_jwk,
        "cachetools": _make_module("cachetools", TTLCache=dict),
    }
    for name, mod in mods.items():
        if name not in sys.modules:
            sys.modules[name] = mod


_register_all()

# ── Pre-import project modules so patch() can resolve dotted targets ───────────
# These imports run successfully because all heavy deps are now stubbed above.
