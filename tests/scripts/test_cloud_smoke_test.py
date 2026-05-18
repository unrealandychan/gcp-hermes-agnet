from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.demo import cloud_smoke_test as mod


def test_probe_gateway_success_parses_sse_done():
    response = MagicMock()
    response.status_code = 200
    response.text = '\n'.join([
        'data: {"type":"text","content":"hello"}',
        'data: {"type":"done","session_id":"s1"}',
    ])

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = response

    with patch.object(mod.httpx, "Client", return_value=mock_client):
        result = mod.probe_gateway(
            gateway_url="https://gateway.example.com",
            message="ping",
            bearer_token="token",
            api_key="",
            timeout_s=10,
        )

    assert result.ok is True
    assert result.mode == "gateway"
    assert "gateway chat ok" in result.detail


def test_probe_gateway_fails_on_http_error():
    response = MagicMock()
    response.status_code = 401
    response.text = "unauthorized"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = response

    with patch.object(mod.httpx, "Client", return_value=mock_client):
        result = mod.probe_gateway(
            gateway_url="https://gateway.example.com",
            message="ping",
            bearer_token="",
            api_key="",
            timeout_s=10,
        )

    assert result.ok is False
    assert "HTTP 401" in result.detail


def test_probe_sdk_success_uses_existing_engine_by_name():
    remote_agent = MagicMock()
    remote_agent.query.return_value = SimpleNamespace(text="ok from cloud")
    sdk_client = MagicMock()
    sdk_client.get_reasoning_engine.return_value = remote_agent

    with patch.object(mod.vertexai, "init") as mock_init:
        result = mod.probe_sdk(
            project_id="p1",
            location="us-central1",
            reasoning_engine_resource_name="projects/p1/locations/us-central1/reasoningEngines/abc",
            user_id="u1",
            message="ping",
            client_factory=lambda: sdk_client,
        )

    assert result.ok is True
    assert result.mode == "sdk"
    assert "sdk query ok" in result.detail
    mock_init.assert_called_once_with(project="p1", location="us-central1")
    sdk_client.get_reasoning_engine.assert_called_once_with(
        name="projects/p1/locations/us-central1/reasoningEngines/abc"
    )
    remote_agent.query.assert_called_once_with(user_id="u1", message="ping")


def test_main_gateway_missing_url_fails():
    exit_code = mod.main(["--mode", "gateway", "--gateway-url", ""])
    assert exit_code == 1
