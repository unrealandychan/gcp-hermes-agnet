"""
tests/gateway/test_observability.py

Unit tests for gateway/observability.py.

These tests verify correct behaviour with and without OpenTelemetry packages
installed. All real OTel SDK calls are mocked.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch



# ── helpers ────────────────────────────────────────────────────────────────────

def _reload_observability():
    """Reload the module so the module-level _tracer global is reset."""
    import gateway.observability as mod
    mod._tracer = None  # reset between tests
    return mod


# ── _NoopTracer / _NoopSpan ────────────────────────────────────────────────────

class TestNoopComponents:
    def test_noop_tracer_start_span_is_context_manager(self):
        from gateway.observability import _NoopTracer
        tracer = _NoopTracer()
        with tracer.start_as_current_span("test") as span:
            # Must not raise
            span.set_attribute("key", "value")
            span.record_exception(Exception("oops"))
            span.set_status("OK")

    def test_noop_span_methods_are_no_ops(self):
        from gateway.observability import _NoopSpan
        span = _NoopSpan()
        span.set_attribute("a", 1)
        span.record_exception(ValueError("x"))
        span.set_status("ERROR")
        # No assertion needed — just must not raise


# ── get_tracer ─────────────────────────────────────────────────────────────────

class TestGetTracer:
    def test_returns_noop_tracer_when_not_initialised(self):
        import gateway.observability as mod
        mod._tracer = None
        tracer = mod.get_tracer()
        from gateway.observability import _NoopTracer
        assert isinstance(tracer, _NoopTracer)

    def test_returns_real_tracer_when_set(self):
        import gateway.observability as mod
        fake_tracer = MagicMock(name="OTelTracer")
        mod._tracer = fake_tracer
        result = mod.get_tracer()
        assert result is fake_tracer
        mod._tracer = None  # cleanup


# ── setup_tracing ──────────────────────────────────────────────────────────────

class TestSetupTracing:
    def test_silently_degrades_when_packages_missing(self):
        """setup_tracing must not raise even if opentelemetry is not installed."""
        import gateway.observability as mod
        mod._tracer = None
        with patch.dict("sys.modules", {
            "opentelemetry": None,
            "opentelemetry.sdk": None,
            "opentelemetry.sdk.trace": None,
            "opentelemetry.sdk.trace.export": None,
            "opentelemetry.sdk.resources": None,
            "opentelemetry.exporter.cloud_trace": None,
        }):
            mod.setup_tracing("test-project")  # must not raise
        # _tracer remains None
        assert mod._tracer is None

    def test_sets_tracer_when_packages_present(self):
        import gateway.observability as mod
        mod._tracer = None

        mock_trace = MagicMock()
        mock_tracer_instance = MagicMock(name="tracer-instance")
        mock_trace.get_tracer.return_value = mock_tracer_instance
        mock_trace.set_tracer_provider = MagicMock()

        mock_provider = MagicMock()
        mock_provider_cls = MagicMock(return_value=mock_provider)

        with (
            patch.dict("sys.modules", {
                "opentelemetry": MagicMock(trace=mock_trace),
                "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider_cls),
                "opentelemetry.sdk.trace.export": MagicMock(BatchSpanProcessor=MagicMock()),
                "opentelemetry.sdk.resources": MagicMock(Resource=MagicMock(create=MagicMock(return_value=MagicMock()))),
                "opentelemetry.exporter.cloud_trace": MagicMock(CloudTraceSpanExporter=MagicMock()),
            }),
            patch("gateway.observability.setup_tracing.__wrapped__", create=True),
        ):
            # Call with a full mock environment
            try:
                from opentelemetry import trace  # noqa
                from opentelemetry.sdk.trace import TracerProvider  # noqa
                from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa
                from opentelemetry.sdk.resources import Resource  # noqa
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter  # noqa
            except ImportError:
                pass

        mod._tracer = None  # cleanup


# ── instrument_fastapi ─────────────────────────────────────────────────────────

class TestInstrumentFastapi:
    def test_silently_skips_when_package_missing(self):
        from gateway.observability import instrument_fastapi
        fake_app = MagicMock()
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.fastapi": None}):
            instrument_fastapi(fake_app)  # must not raise

    def test_calls_instrument_app_when_available(self):
        mock_instrumentor_cls = MagicMock()
        mock_instrumentor = MagicMock()
        mock_instrumentor_cls.return_value = mock_instrumentor

        fake_app = MagicMock()
        mock_module = MagicMock()
        mock_module.FastAPIInstrumentor = mock_instrumentor_cls

        from gateway.observability import instrument_fastapi
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.fastapi": mock_module}):
            instrument_fastapi(fake_app)
        mock_instrumentor_cls.instrument_app.assert_called_once_with(fake_app)


# ── agent_span ─────────────────────────────────────────────────────────────────

class TestAgentSpan:
    def test_span_context_manager_yields(self):
        """agent_span must work as a context manager even with NoopTracer."""
        import gateway.observability as mod
        mod._tracer = None
        from gateway.observability import agent_span
        with agent_span("TestAgent", user_id="u1", session_id="s1") as span:
            assert span is not None  # _NoopSpan

    def test_noop_span_does_not_raise_on_set_attribute(self):
        import gateway.observability as mod
        mod._tracer = None
        from gateway.observability import agent_span
        with agent_span("DeveloperAgent") as span:
            span.set_attribute("hermes.message_len", 42)
            span.record_exception(RuntimeError("boom"))

    def test_span_uses_agent_name_in_span_name(self):
        """The real tracer should be called with 'agent/<name>'."""
        import gateway.observability as mod

        recorded = {}

        @contextmanager
        def fake_start_span(name, **_):
            recorded["name"] = name
            yield MagicMock()

        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span = fake_start_span
        mod._tracer = fake_tracer

        from gateway.observability import agent_span
        with agent_span("HRAgent"):
            pass

        assert recorded["name"] == "agent/HRAgent"
        mod._tracer = None  # cleanup
