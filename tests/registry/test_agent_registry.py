"""Offline unit tests for registry/agent_registry.py (Issue #8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from registry.agent_registry import AgentRecord, HermesAgentRegistry, build_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(name: str = "TestAgent") -> AgentRecord:
    return AgentRecord(
        name=name,
        description="A test agent",
        agent_type="custom",
        endpoint="https://example.com",
        version="1.2.3",
        tags=["test", "example"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_agent_returns_resource_id():
    registry = HermesAgentRegistry()
    with patch.dict("sys.modules", {"vertexai": MagicMock(), "vertexai.preview": MagicMock(), "vertexai.preview.reasoning_engines": MagicMock()}):
        record = make_record("MyAgent")
        resource_id = await registry.register_agent(record)
    assert "MyAgent" in resource_id


@pytest.mark.asyncio
async def test_list_agents_returns_registered():
    registry = HermesAgentRegistry()
    record = make_record("AgentAlpha")
    registry._local["AgentAlpha"] = record  # seed local cache directly
    with patch.dict("sys.modules", {"vertexai": MagicMock(), "vertexai.preview": MagicMock(), "vertexai.preview.reasoning_engines": MagicMock()}):
        agents = await registry.list_agents()
    assert any(a.name == "AgentAlpha" for a in agents)


@pytest.mark.asyncio
async def test_get_agent_found():
    registry = HermesAgentRegistry()
    record = make_record("AgentBeta")
    registry._local["AgentBeta"] = record
    with patch.dict("sys.modules", {"vertexai": MagicMock(), "vertexai.preview": MagicMock(), "vertexai.preview.reasoning_engines": MagicMock()}):
        found = await registry.get_agent("AgentBeta")
    assert found is not None
    assert found.name == "AgentBeta"


@pytest.mark.asyncio
async def test_get_agent_not_found():
    registry = HermesAgentRegistry()
    with patch.dict("sys.modules", {"vertexai": MagicMock(), "vertexai.preview": MagicMock(), "vertexai.preview.reasoning_engines": MagicMock()}):
        found = await registry.get_agent("NonExistent")
    assert found is None


@pytest.mark.asyncio
async def test_register_fallback_when_vertex_unavailable():
    """When Vertex AI import fails, registry should fall back gracefully."""
    registry = HermesAgentRegistry()
    with patch.dict("sys.modules", {"vertexai": None, "vertexai.preview": None, "vertexai.preview.reasoning_engines": None}):
        record = make_record("FallbackAgent")
        resource_id = await registry.register_agent(record)
    # Falls back to local:// scheme
    assert resource_id.startswith("local://") or "FallbackAgent" in resource_id


def test_agent_record_defaults():
    record = AgentRecord(name="X", description="desc")
    assert record.agent_type == "custom"
    assert record.endpoint == ""
    assert record.version == "1.0.0"
    assert record.tags == []


def test_build_registry_returns_instance():
    registry = build_registry()
    assert registry is not None
    assert isinstance(registry, HermesAgentRegistry)


@pytest.mark.asyncio
async def test_multiple_agents_registered_and_listed():
    registry = HermesAgentRegistry()
    names = ["Agent1", "Agent2", "Agent3"]
    for n in names:
        registry._local[n] = make_record(n)
    with patch.dict("sys.modules", {"vertexai": MagicMock(), "vertexai.preview": MagicMock(), "vertexai.preview.reasoning_engines": MagicMock()}):
        agents = await registry.list_agents()
    listed_names = [a.name for a in agents]
    for n in names:
        assert n in listed_names
