"""
tests/gateway/test_agent_gateway.py

Offline unit tests for gateway/agent_gateway.py (Issue #9).

All network calls are mocked — no real HTTP or GCP required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


from gateway.agent_gateway import (
    AgentGatewayClient,
    AgentGatewayConfig,
    build_agent_gateway,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _enabled_config(**kwargs) -> AgentGatewayConfig:
    defaults = dict(endpoint="https://gateway.example.com", api_key="test-key")
    defaults.update(kwargs)
    return AgentGatewayConfig(**defaults)


def _disabled_config() -> AgentGatewayConfig:
    return AgentGatewayConfig()  # no endpoint


# ── AgentGatewayConfig ─────────────────────────────────────────────────────────

class TestAgentGatewayConfig:
    def test_enabled_when_endpoint_set(self):
        cfg = _enabled_config()
        assert cfg.enabled is True

    def test_disabled_when_no_endpoint(self):
        cfg = _disabled_config()
        assert cfg.enabled is False

    def test_defaults(self):
        cfg = AgentGatewayConfig()
        assert cfg.timeout_seconds == 60
        assert cfg.model_armor_delegate is True
        assert cfg.api_key == ""


# ── AgentGatewayClient.send_message ───────────────────────────────────────────

class TestSendMessage:
    async def test_returns_none_when_disabled(self):
        client = AgentGatewayClient(_disabled_config())
        result = await client.send_message("u1", "s1", "hello")
        assert result is None

    async def test_calls_post_and_returns_json(self):
        cfg = _enabled_config()
        client = AgentGatewayClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"reply": "ok"}
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_httpx_client

        result = await client.send_message("u1", "s1", "hello")
        assert result == {"reply": "ok"}
        mock_httpx_client.post.assert_called_once()

    async def test_returns_none_on_http_error(self):
        cfg = _enabled_config()
        client = AgentGatewayClient(cfg)

        mock_httpx_client = AsyncMock()
        mock_httpx_client.post = AsyncMock(side_effect=Exception("connection refused"))
        client._client = mock_httpx_client

        # Should NOT raise — graceful fallback
        result = await client.send_message("u1", "s1", "hello")
        assert result is None

    async def test_includes_reasoning_engine_id_in_payload(self):
        cfg = _enabled_config(reasoning_engine_id="projects/p/locations/l/reasoningEngines/r")
        client = AgentGatewayClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"reply": "ok"}
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)
        client._client = mock_httpx_client

        await client.send_message("u1", "s1", "hello", agent_name="HRAgent")

        call_kwargs = mock_httpx_client.post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload["reasoning_engine_id"] == "projects/p/locations/l/reasoningEngines/r"
        assert payload["agent_name"] == "HRAgent"


# ── AgentGatewayClient.stream_message ─────────────────────────────────────────

class TestStreamMessage:
    async def test_yields_nothing_when_disabled(self):
        client = AgentGatewayClient(_disabled_config())
        chunks = [c async for c in client.stream_message("u1", "s1", "hello")]
        assert chunks == []

    async def test_yields_data_lines(self):
        cfg = _enabled_config()
        client = AgentGatewayClient(cfg)

        # Build a mock async context manager for client.stream()
        async def _aiter_lines():
            for line in ["data: chunk1", "data: chunk2", "not-data"]:
                yield line

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = _aiter_lines

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_stream(*args, **kwargs):
            yield mock_resp

        mock_httpx_client = MagicMock()
        mock_httpx_client.stream = _mock_stream
        client._client = mock_httpx_client

        chunks = [c async for c in client.stream_message("u1", "s1", "hi")]
        assert chunks == ["chunk1", "chunk2"]  # "not-data" filtered out

    async def test_stream_error_yields_nothing(self):
        cfg = _enabled_config()
        client = AgentGatewayClient(cfg)

        mock_httpx_client = MagicMock()
        mock_httpx_client.stream.side_effect = Exception("network error")
        client._client = mock_httpx_client

        # Should not raise
        chunks = [c async for c in client.stream_message("u1", "s1", "hi")]
        assert chunks == []


# ── AgentGatewayClient.close ──────────────────────────────────────────────────

class TestClose:
    async def test_close_calls_aclose(self):
        cfg = _enabled_config()
        client = AgentGatewayClient(cfg)
        mock_httpx_client = AsyncMock()
        client._client = mock_httpx_client

        await client.close()
        mock_httpx_client.aclose.assert_called_once()
        assert client._client is None

    async def test_close_noop_when_not_initialised(self):
        client = AgentGatewayClient(_disabled_config())
        # Should not raise
        await client.close()


# ── build_agent_gateway ────────────────────────────────────────────────────────

class TestBuildAgentGateway:
    def test_returns_disabled_client_when_no_env(self):
        with patch("config.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.agent_gateway_endpoint = ""
            mock_s.agent_gateway_api_key = ""
            mock_s.reasoning_engine_resource_name = ""
            mock_s.agent_gateway_timeout_seconds = 60
            mock_s.agent_gateway_model_armor_delegate = True
            mock_settings.return_value = mock_s

            client = build_agent_gateway()
            assert client._config.enabled is False

    def test_returns_enabled_client_when_endpoint_set(self):
        with patch("config.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.agent_gateway_endpoint = "https://gw.example.com"
            mock_s.agent_gateway_api_key = "key123"
            mock_s.reasoning_engine_resource_name = "projects/p/..."
            mock_s.agent_gateway_timeout_seconds = 30
            mock_s.agent_gateway_model_armor_delegate = False
            mock_settings.return_value = mock_s

            client = build_agent_gateway()
            assert client._config.enabled is True
            assert client._config.endpoint == "https://gw.example.com"
            assert client._config.timeout_seconds == 30

    def test_returns_disabled_client_on_settings_error(self):
        with patch("config.get_settings", side_effect=RuntimeError("settings error")):
            client = build_agent_gateway()
            assert client._config.enabled is False
