"""
gateway/agent_gateway.py

Thin wrapper for routing agent requests through the Gemini Enterprise
Agent Platform's Agent Gateway.

Agent Gateway provides:
- Centralised security policy enforcement (Model Armor, Semantic Gov)
- Governed routing between clients and Vertex AI Reasoning Engine
- Audit logging at the gateway layer (not ad-hoc in each endpoint)
- Private Service Connect (PSC) support for VPC-isolated deployments

When AGENT_GATEWAY_ENDPOINT is set, the /chat endpoint routes through the
gateway instead of calling runner.run_async() directly.
When unset, the gateway falls back to direct Runner execution (existing
behaviour) so local dev and CI require no extra setup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class AgentGatewayConfig:
    """
    Configuration for Agent Gateway routing.

    All fields are optional — unset fields cause graceful fallback to
    direct Runner execution.
    """
    endpoint: str = ""
    """Agent Gateway endpoint URL.  E.g. https://agent-gateway-PROJECT.run.app"""

    api_key: str = ""
    """API key for Agent Gateway (if required by the deployment)."""

    reasoning_engine_id: str = ""
    """Vertex AI Reasoning Engine resource name routed through the gateway."""

    timeout_seconds: int = 60
    """Per-request timeout for gateway calls."""

    model_armor_delegate: bool = True
    """
    When True, Model Armor screening is delegated to the gateway layer.
    The inline tools/model_armor.py calls are skipped to avoid double-screening.
    """

    enabled: bool = field(init=False)

    def __post_init__(self) -> None:
        self.enabled = bool(self.endpoint)


# ── Gateway client ─────────────────────────────────────────────────────────────

class AgentGatewayClient:
    """
    Async client for sending chat requests via Agent Gateway.

    When gateway is disabled (config.enabled == False), all methods
    return None and the caller falls back to direct Runner execution.
    """

    def __init__(self, config: AgentGatewayConfig) -> None:
        self._config = config
        self._client: Any = None  # httpx.AsyncClient, lazy-init

    def _ensure_client(self):
        if self._client is None:
            try:
                import httpx
                headers = {"Content-Type": "application/json"}
                if self._config.api_key:
                    headers["Authorization"] = f"Bearer {self._config.api_key}"
                self._client = httpx.AsyncClient(
                    base_url=self._config.endpoint,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
            except ImportError as exc:
                raise ImportError(
                    "httpx is required for Agent Gateway. "
                    "Run: pip install httpx"
                ) from exc
        return self._client

    async def send_message(
        self,
        user_id: str,
        session_id: str,
        message: str,
        agent_name: str = "",
    ) -> dict | None:
        """
        Send a message via Agent Gateway and return the JSON response.

        Returns None if the gateway is disabled or the call fails (graceful fallback).
        """
        if not self._config.enabled:
            return None

        client = self._ensure_client()
        payload: dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
        }
        if agent_name:
            payload["agent_name"] = agent_name
        if self._config.reasoning_engine_id:
            payload["reasoning_engine_id"] = self._config.reasoning_engine_id

        try:
            response = await client.post("/v1/chat", json=payload)
            response.raise_for_status()
            result: dict = response.json()
            logger.debug(
                "AgentGateway response: user=%s session=%s status=%d",
                user_id, session_id, response.status_code,
            )
            return result
        except Exception:  # noqa: BLE001
            logger.exception(
                "AgentGateway request failed — falling back to direct runner. "
                "user=%s session=%s",
                user_id, session_id,
            )
            return None

    async def stream_message(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> AsyncIterator[str]:
        """
        Stream SSE events from Agent Gateway.

        Falls back to empty iterator if gateway is disabled or fails.
        The caller (gateway/main.py) detects the empty iterator and uses
        the direct ADK runner instead.
        """
        if not self._config.enabled:
            return

        client = self._ensure_client()
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "stream": True,
        }
        if self._config.reasoning_engine_id:
            payload["reasoning_engine_id"] = self._config.reasoning_engine_id

        try:
            async with client.stream("POST", "/v1/chat/stream", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line.removeprefix("data: ")
        except Exception:  # noqa: BLE001
            logger.exception(
                "AgentGateway stream failed — caller should fall back to direct runner. "
                "user=%s session=%s", user_id, session_id,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client. Call on app shutdown."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ── Factory ────────────────────────────────────────────────────────────────────

def build_agent_gateway() -> AgentGatewayClient:
    """
    Build an AgentGatewayClient from settings.

    Returns a disabled client (config.enabled=False) when
    AGENT_GATEWAY_ENDPOINT is not set, so all calls fall through
    to direct Runner execution transparently.
    """
    try:
        from config import get_settings
        settings = get_settings()
        config = AgentGatewayConfig(
            endpoint=getattr(settings, "agent_gateway_endpoint", ""),
            api_key=getattr(settings, "agent_gateway_api_key", ""),
            reasoning_engine_id=getattr(settings, "reasoning_engine_resource_name", ""),
            timeout_seconds=getattr(settings, "agent_gateway_timeout_seconds", 60),
            model_armor_delegate=getattr(settings, "agent_gateway_model_armor_delegate", True),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to build AgentGatewayConfig — gateway disabled.")
        config = AgentGatewayConfig()

    client = AgentGatewayClient(config)
    if config.enabled:
        logger.info("Agent Gateway enabled: endpoint=%s", config.endpoint)
    else:
        logger.info("Agent Gateway disabled — using direct Vertex AI Runner.")
    return client
