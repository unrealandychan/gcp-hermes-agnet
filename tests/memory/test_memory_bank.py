"""
tests/memory/test_memory_bank.py

Comprehensive offline unit tests for memory/memory_bank.py.

All GCP/Vertex AI SDK calls are mocked via:
    patch('memory.memory_bank._get_vertexai_client')

No real credentials or network access are needed.

Migration note (SDK >= 1.112):
    The old `vertexai.preview.memory_bank.MemoryBank` class no longer exists.
    All memory operations now go through `vertexai.Client.agent_engines.memories.*`.
    Tests mock `_get_vertexai_client` and assert against the new API surface.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from memory.memory_bank import (
    HermesMemoryBank,
    build_memory_bank,
    create_memory_bank,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_client():
    """Return a (mock_client, mock_memories) pair for new vertexai.Client API."""
    mock_memories = MagicMock()
    mock_agent_engines = MagicMock()
    mock_agent_engines.memories = mock_memories
    mock_client = MagicMock()
    mock_client.agent_engines = mock_agent_engines
    return mock_client, mock_memories


def _make_engine(resource_name: str, display_name: str = "hermes-memory-bank"):
    """
    Build a mock AgentEngine that mirrors the SDK >= 1.112 structure:
      engine.api_resource.name         → resource_name
      engine.api_resource.display_name → display_name
    """
    api_resource = SimpleNamespace(name=resource_name, display_name=display_name)
    return SimpleNamespace(api_resource=api_resource)


def _make_memory(fact: str):
    return SimpleNamespace(fact=fact)


# ── HermesMemoryBank.generate_memories ────────────────────────────────────────

class TestGenerateMemories:

    async def test_success_calls_memories_generate(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            await bank.generate_memories(
                user_id="u1",
                user_text="How do I reset my VPN?",
                agent_text="Go to Settings > VPN > Reset.",
            )
        mock_memories.generate.assert_called_once()
        call_kwargs = mock_memories.generate.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert call_kwargs["name"] == "projects/p/reasoningEngines/123"
        events = call_kwargs["direct_contents_source"]["events"]
        # Events are now Content objects (not dicts) — access via .role attribute
        assert any(e.role == "user" for e in events)
        assert any(e.role == "model" for e in events)

    async def test_success_with_agent_name_in_events(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            await bank.generate_memories(
                user_id="u1",
                user_text="Hello",
                agent_text="Hi there",
                agent_name="HelpDeskAgent",
            )
        call_kwargs = mock_memories.generate.call_args[1]
        events = call_kwargs["direct_contents_source"]["events"]
        # Events are now Content objects — use .role and .parts[0].text
        model_event = next(e for e in events if e.role == "model")
        assert "Hi there" in model_event.parts[0].text

    async def test_exception_is_swallowed(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.generate.side_effect = RuntimeError("SDK failure")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            # Should not raise; exception is logged and swallowed
            await bank.generate_memories(
                user_id="u1",
                user_text="test",
                agent_text="response",
            )

    async def test_client_is_lazily_initialised(self):
        mock_client, _ = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client) as mock_factory:
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            assert bank._client is None
            await bank.generate_memories(user_id="u1", user_text="x", agent_text="y")
        mock_factory.assert_called_once()
        assert bank._client is not None


# ── HermesMemoryBank.fetch_memories ───────────────────────────────────────────

class TestFetchMemories:

    async def test_returns_fact_strings(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.return_value = iter([
            _make_memory("User prefers dark mode"),
            _make_memory("Team is EMEA"),
        ])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.fetch_memories(user_id="u1", query="preferences")
        assert result == ["User prefers dark mode", "Team is EMEA"]

    async def test_returns_empty_list_on_error(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.side_effect = Exception("network error")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.fetch_memories(user_id="u1", query="anything")
        assert result == []

    async def test_passes_top_k_and_scope_to_sdk(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.return_value = iter([])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            await bank.fetch_memories(user_id="u1", query="q", top_k=3)
        call_kwargs = mock_memories.retrieve.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert call_kwargs["similarity_search_params"]["top_k"] == 3

    async def test_memory_without_fact_attr_falls_back_to_str(self):
        mock_client, mock_memories = _make_mock_client()
        raw = object.__new__(object)  # plain object, no .fact
        mock_memories.retrieve.return_value = iter([raw])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.fetch_memories(user_id="u1", query="q")
        assert len(result) == 1
        assert isinstance(result[0], str)


# ── HermesMemoryBank.list_revisions ───────────────────────────────────────────

class TestListRevisions:

    async def test_returns_empty_list(self):
        """list_revisions is not supported in SDK >= 1.112 — always returns []."""
        mock_client, _ = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.list_revisions(user_id="u1")
        assert result == []


# ── HermesMemoryBank.format_for_prompt ────────────────────────────────────────

class TestFormatForPrompt:

    async def test_returns_formatted_string_with_header(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.return_value = iter([
            _make_memory("Prefers Python"),
            _make_memory("Works in EMEA"),
        ])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.format_for_prompt(user_id="u1", query="context")
        assert result.startswith("## User Memory (long-term context)")
        assert "- Prefers Python" in result
        assert "- Works in EMEA" in result

    async def test_returns_empty_string_when_no_memories(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.return_value = iter([])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.format_for_prompt(user_id="u1", query="q")
        assert result == ""

    async def test_returns_empty_string_when_fetch_fails(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.retrieve.side_effect = Exception("error")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.format_for_prompt(user_id="u1", query="q")
        assert result == ""

    async def test_respects_max_tokens_budget(self):
        mock_client, mock_memories = _make_mock_client()
        mem_a = "A" * 100
        mem_b = "B" * 100
        mock_memories.retrieve.return_value = iter([
            _make_memory(mem_a),
            _make_memory(mem_b),
        ])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            # max_tokens=25 → char_budget = 100, exactly fits mem_a but not both
            result = await bank.format_for_prompt(user_id="u1", query="q", max_tokens=25)
        assert mem_a in result
        assert mem_b not in result


# ── build_memory_bank ─────────────────────────────────────────────────────────

class TestBuildMemoryBank:

    def test_returns_none_when_resource_name_not_set(self):
        mock_settings = SimpleNamespace(memory_bank_resource_name=None)
        import config
        original = config.get_settings
        config.get_settings = lambda: mock_settings
        try:
            result = build_memory_bank()
        finally:
            config.get_settings = original
        assert result is None

    def test_returns_none_when_resource_name_is_empty_string(self):
        mock_settings = SimpleNamespace(memory_bank_resource_name="")
        import config
        original = config.get_settings
        config.get_settings = lambda: mock_settings
        try:
            result = build_memory_bank()
        finally:
            config.get_settings = original
        assert result is None

    def test_returns_hermes_memory_bank_when_configured(self):
        mock_settings = SimpleNamespace(
            memory_bank_resource_name="projects/p/locations/l/reasoningEngines/123"
        )
        import config
        original = config.get_settings
        config.get_settings = lambda: mock_settings
        try:
            result = build_memory_bank()
        finally:
            config.get_settings = original
        assert isinstance(result, HermesMemoryBank)
        assert result._resource_name == "projects/p/locations/l/reasoningEngines/123"

    def test_returns_none_on_exception(self):
        import config
        original = config.get_settings
        config.get_settings = MagicMock(side_effect=RuntimeError("settings failure"))
        try:
            result = build_memory_bank()
        finally:
            config.get_settings = original
        assert result is None


# ── create_memory_bank ────────────────────────────────────────────────────────

class TestCreateMemoryBank:

    def test_creates_and_returns_resource_name(self):
        mock_client, _ = _make_mock_client()
        new_engine = _make_engine("projects/p/locations/us-central1/reasoningEngines/new")
        mock_client.agent_engines.list.return_value = iter([])
        mock_client.agent_engines.create.return_value = new_engine
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            result = create_memory_bank(project="p", location="us-central1")
        assert result == "projects/p/locations/us-central1/reasoningEngines/new"
        mock_client.agent_engines.create.assert_called_once()

    def test_returns_existing_engine_when_display_name_matches(self):
        mock_client, _ = _make_mock_client()
        existing = _make_engine(
            "projects/p/locations/us-central1/reasoningEngines/existing",
            display_name="hermes-memory-bank",
        )
        mock_client.agent_engines.list.return_value = iter([existing])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            result = create_memory_bank(project="p", location="us-central1")
        assert result == "projects/p/locations/us-central1/reasoningEngines/existing"
        mock_client.agent_engines.create.assert_not_called()

    def test_skips_non_matching_display_name_in_list(self):
        mock_client, _ = _make_mock_client()
        other = _make_engine("projects/p/reasoningEngines/other", display_name="some-other-engine")
        new_engine = _make_engine("projects/p/reasoningEngines/new")
        mock_client.agent_engines.list.return_value = iter([other])
        mock_client.agent_engines.create.return_value = new_engine
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            result = create_memory_bank(
                project="p", location="us-central1", display_name="hermes-memory-bank"
            )
        assert result == "projects/p/reasoningEngines/new"
        mock_client.agent_engines.create.assert_called_once()

    def test_uses_custom_display_name(self):
        mock_client, _ = _make_mock_client()
        new_engine = _make_engine("projects/p/reasoningEngines/custom", display_name="my-custom-bank")
        mock_client.agent_engines.list.return_value = iter([])
        mock_client.agent_engines.create.return_value = new_engine
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            result = create_memory_bank(
                project="p", location="us-central1", display_name="my-custom-bank"
            )
        assert result == "projects/p/reasoningEngines/custom"
        call_kwargs = mock_client.agent_engines.create.call_args[1]
        assert call_kwargs["config"]["display_name"] == "my-custom-bank"

    def test_proceeds_to_create_when_list_raises(self):
        mock_client, _ = _make_mock_client()
        mock_client.agent_engines.list.side_effect = Exception("permission denied on list")
        new_engine = _make_engine("projects/p/reasoningEngines/new")
        mock_client.agent_engines.create.return_value = new_engine
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            result = create_memory_bank(project="p", location="us-central1")
        assert result == "projects/p/reasoningEngines/new"


# ── HermesMemoryBank.ingest_events ────────────────────────────────────────────

class TestIngestEvents:

    async def test_calls_memories_ingest_events(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            await bank.ingest_events(
                user_id="u1",
                events=[
                    {"role": "user", "text": "How do I reset VPN?"},
                    {"role": "agent", "text": "Go to Settings > VPN > Reset."},
                ],
            )
        mock_memories.ingest_events.assert_called_once()
        call_kwargs = mock_memories.ingest_events.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        events = call_kwargs["direct_contents_source"]["events"]
        assert len(events) == 2
        # Events are now Content objects — use .role attribute
        # 'agent' role is normalised to 'model'
        assert events[1].role == "model"

    async def test_normalises_agent_role_to_model(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            await bank.ingest_events(
                user_id="u1",
                events=[{"role": "agent", "text": "hello"}],
            )
        events = mock_memories.ingest_events.call_args[1]["direct_contents_source"]["events"]
        # Events are now Content objects — use .role attribute
        assert events[0].role == "model"

    async def test_exception_is_swallowed(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.ingest_events.side_effect = RuntimeError("sdk error")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            # Should not raise
            await bank.ingest_events(user_id="u1", events=[{"role": "user", "text": "hi"}])


# ── HermesMemoryBank.purge_memories ───────────────────────────────────────────

class TestPurgeMemories:

    async def test_calls_purge_with_force_true(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.list.return_value = iter([MagicMock(), MagicMock(), MagicMock()])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            count = await bank.purge_memories(user_id="u1")
        assert count == 3
        mock_memories.purge.assert_called_once()
        call_kwargs = mock_memories.purge.call_args[1]
        assert call_kwargs["force"] is True  # dry_run=False → force=True

    async def test_dry_run_skips_purge_call(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.list.return_value = iter([MagicMock(), MagicMock()])
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            count = await bank.purge_memories(user_id="u1", dry_run=True)
        assert count == 2
        mock_memories.purge.assert_not_called()

    async def test_returns_zero_on_exception(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.list.side_effect = RuntimeError("quota error")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            count = await bank.purge_memories(user_id="u1")
        assert count == 0


# ── HermesMemoryBank.delete_memory ────────────────────────────────────────────

class TestDeleteMemory:

    async def test_calls_memories_delete(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.delete_memory("projects/p/reasoningEngines/123/memories/m1")
        assert result is True
        mock_memories.delete.assert_called_once_with(
            name="projects/p/reasoningEngines/123/memories/m1"
        )

    async def test_returns_false_on_exception(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.delete.side_effect = RuntimeError("not found")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.delete_memory("projects/p/reasoningEngines/123/memories/m1")
        assert result is False


# ── HermesMemoryBank.create_memory ────────────────────────────────────────────

class TestCreateMemory:

    async def test_calls_memories_create_and_returns_name(self):
        mock_client, mock_memories = _make_mock_client()
        created = SimpleNamespace(name="projects/p/reasoningEngines/123/memories/new")
        mock_memories.create.return_value = created
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.create_memory(user_id="u1", fact="User is based in HK")
        assert result == "projects/p/reasoningEngines/123/memories/new"
        call_kwargs = mock_memories.create.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert call_kwargs["fact"] == "User is based in HK"
        assert call_kwargs["name"] == "projects/p/reasoningEngines/123"

    async def test_returns_none_on_exception(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.create.side_effect = RuntimeError("sdk error")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.create_memory(user_id="u1", fact="some fact")
        assert result is None


# ── HermesMemoryBank.update_memory ────────────────────────────────────────────

class TestUpdateMemory:

    async def test_calls_memories_update(self):
        mock_client, mock_memories = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.update_memory(
                memory_resource_name="projects/p/reasoningEngines/123/memories/m1",
                new_fact="Updated fact",
            )
        assert result is True
        mock_memories.update.assert_called_once_with(
            name="projects/p/reasoningEngines/123/memories/m1",
            fact="Updated fact",
        )

    async def test_returns_false_on_exception(self):
        mock_client, mock_memories = _make_mock_client()
        mock_memories.update.side_effect = RuntimeError("not found")
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.update_memory("projects/p/.../m1", "fact")
        assert result is False


# ── HermesMemoryBank.retrieve_profiles ────────────────────────────────────────

class TestRetrieveProfiles:

    async def test_returns_empty_list(self):
        """retrieve_profiles is not supported in SDK >= 1.112 — always returns []."""
        mock_client, _ = _make_mock_client()
        with patch("memory.memory_bank._get_vertexai_client", return_value=mock_client):
            bank = HermesMemoryBank(resource_name="projects/p/reasoningEngines/123")
            result = await bank.retrieve_profiles(user_id="u1")
        assert result == []
