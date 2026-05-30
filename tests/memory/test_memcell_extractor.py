"""
tests/memory/test_memcell_extractor.py

Unit tests for MemCell extractor — fully offline, ADK/LLM mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.memcell_models import MemCell, MemoryType
from memory.memcell_extractor import _parse_memcell, extract_memcell


# ── _parse_memcell unit tests (pure, no I/O) ──────────────────────────────────

class TestParseMemcell:
    def test_parses_full_valid_json(self):
        raw = """{
          "memory_type": "preference",
          "episode": "The user told the HR agent they prefer async communication.",
          "facts": ["User prefers async communication over meetings."],
          "foresight": [
            {"inference": "User may decline meeting requests", "valid_until": null}
          ]
        }"""
        cell = _parse_memcell(raw, agent_name="HRAgent", user_id="u1")
        assert cell is not None
        assert cell.memory_type == MemoryType.PREFERENCE
        assert "async" in cell.episode
        assert len(cell.facts) == 1
        assert len(cell.foresight) == 1
        assert cell.agent_name == "HRAgent"
        assert cell.user_id == "u1"

    def test_returns_none_on_non_json(self):
        cell = _parse_memcell("NO_MEMORY", agent_name="A", user_id="u1")
        assert cell is None

    def test_returns_none_on_empty(self):
        cell = _parse_memcell("", agent_name="A", user_id="u1")
        assert cell is None

    def test_unknown_memory_type_defaults_to_knowledge(self):
        raw = """{
          "memory_type": "banana",
          "episode": "Something happened.",
          "facts": [],
          "foresight": []
        }"""
        cell = _parse_memcell(raw, agent_name="A", user_id="u1")
        assert cell is not None
        assert cell.memory_type == MemoryType.KNOWLEDGE

    def test_missing_foresight_defaults_to_empty(self):
        raw = """{
          "memory_type": "skill",
          "episode": "Agent ran a query.",
          "facts": ["BigQuery table X has 3M rows."]
        }"""
        cell = _parse_memcell(raw, agent_name="AnalyticsAgent", user_id="u2")
        assert cell is not None
        assert cell.foresight == []

    def test_memcell_id_includes_agent_name(self):
        raw = """{
          "memory_type": "knowledge",
          "episode": "Something.",
          "facts": [],
          "foresight": []
        }"""
        cell = _parse_memcell(raw, agent_name="ITAgent", user_id="u3")
        assert cell is not None
        assert cell.memcell_id.startswith("itagent_")

    def test_json_embedded_in_text(self):
        """Extractor should handle LLM wrapping JSON in prose."""
        raw = 'Here is the result: {"memory_type": "core", "episode": "E.", "facts": [], "foresight": []}'
        cell = _parse_memcell(raw, agent_name="A", user_id="u1")
        assert cell is not None
        assert cell.memory_type == MemoryType.CORE


# ── extract_memcell integration test (ADK mocked) ─────────────────────────────

@pytest.mark.asyncio
async def test_extract_memcell_returns_cell_on_valid_llm_response():
    """extract_memcell should parse a valid LLM response into a MemCell."""

    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_event.content = MagicMock()
    mock_event.content.parts = [
        MagicMock(text='{"memory_type":"skill","episode":"E.","facts":["F1"],"foresight":[]}')
    ]

    async def mock_run_async(**kwargs):
        yield mock_event

    mock_session = MagicMock()
    mock_session.id = "sess-123"

    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    mock_runner = MagicMock()
    mock_runner.session_service = mock_session_service
    mock_runner.run_async = mock_run_async

    with patch("memory.memcell_extractor.InMemoryRunner", return_value=mock_runner), \
         patch("memory.memcell_extractor._get_extractor_agent", return_value=MagicMock()):
        cell = await extract_memcell(
            agent_name="DevAgent",
            user_id="u42",
            user_query="How do I reset my VPN?",
            agent_response="Go to Settings > VPN > Reset.",
        )

    assert cell is not None
    assert isinstance(cell, MemCell)
    assert cell.memory_type == MemoryType.SKILL
    assert "F1" in cell.facts
    assert cell.user_id == "u42"
    assert cell.agent_name == "DevAgent"


@pytest.mark.asyncio
async def test_extract_memcell_returns_none_on_no_memory():
    """extract_memcell returns None when LLM says NO_MEMORY."""

    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="NO_MEMORY")]

    async def mock_run_async(**kwargs):
        yield mock_event

    mock_session = MagicMock()
    mock_session.id = "sess-456"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_runner = MagicMock()
    mock_runner.session_service = mock_session_service
    mock_runner.run_async = mock_run_async

    with patch("memory.memcell_extractor.InMemoryRunner", return_value=mock_runner), \
         patch("memory.memcell_extractor._get_extractor_agent", return_value=MagicMock()):
        cell = await extract_memcell(
            agent_name="HRAgent",
            user_id="u1",
            user_query="Hi",
            agent_response="Hello! How can I help?",
        )

    assert cell is None
