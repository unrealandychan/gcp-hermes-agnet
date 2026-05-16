"""
tests/memory/test_memory_bank.py

Comprehensive offline unit tests for memory/memory_bank.py.

All GCP/Vertex AI SDK calls are mocked via:
    patch('memory.memory_bank._get_memory_bank_module')

No real credentials or network access are needed.
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

def _make_mock_module():
    """Return a fully-faked vertexai.preview.memory_bank module."""
    mock_mb_module = MagicMock()
    mock_bank_instance = MagicMock()
    mock_mb_module.MemoryBank.return_value = mock_bank_instance
    return mock_mb_module, mock_bank_instance


def _make_memory(fact: str):
    return SimpleNamespace(fact=fact)


# ── HermesMemoryBank.generate_memories ────────────────────────────────────────

class TestGenerateMemories:

    async def test_success_calls_bank_generate(self):
        mock_mb, mock_bank = _make_mock_module()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.generate_memories(
                user_id="u1",
                user_text="How do I reset my VPN?",
                agent_text="Go to Settings > VPN > Reset.",
            )
        mock_bank.generate_memories.assert_called_once()
        call_kwargs = mock_bank.generate_memories.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert "User: How do I reset my VPN?" in call_kwargs["conversation"]

    async def test_success_with_agent_name_in_conversation(self):
        mock_mb, mock_bank = _make_mock_module()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.generate_memories(
                user_id="u1",
                user_text="Hello",
                agent_text="Hi there",
                agent_name="HelpDeskAgent",
            )
        call_kwargs = mock_bank.generate_memories.call_args[1]
        assert "Agent (HelpDeskAgent): Hi there" in call_kwargs["conversation"]

    async def test_exception_is_swallowed(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.generate_memories.side_effect = RuntimeError("SDK failure")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            # Should not raise; exception is logged and swallowed
            await bank.generate_memories(
                user_id="u1",
                user_text="test",
                agent_text="response",
            )

    async def test_bank_is_lazily_initialised(self):
        mock_mb, mock_bank = _make_mock_module()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            assert bank._bank is None
            await bank.generate_memories(user_id="u1", user_text="x", agent_text="y")
        mock_mb.MemoryBank.assert_called_once_with(resource_name="projects/p/memoryBanks/b")
        assert bank._bank is not None


# ── HermesMemoryBank.fetch_memories ───────────────────────────────────────────

class TestFetchMemories:

    async def test_returns_fact_strings(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.return_value = SimpleNamespace(
            memories=[_make_memory("User prefers dark mode"), _make_memory("Team is EMEA")]
        )
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.fetch_memories(user_id="u1", query="preferences")
        assert result == ["User prefers dark mode", "Team is EMEA"]

    async def test_returns_empty_list_on_error(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.side_effect = Exception("network error")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.fetch_memories(user_id="u1", query="anything")
        assert result == []

    async def test_passes_top_k_to_sdk(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.return_value = SimpleNamespace(memories=[])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.fetch_memories(user_id="u1", query="q", top_k=3)
        call_kwargs = mock_bank.fetch_memories.call_args[1]
        assert call_kwargs["top_k"] == 3
        assert call_kwargs["scope"] == {"user_id": "u1"}

    async def test_memories_attribute_missing_returns_empty(self):
        mock_mb, mock_bank = _make_mock_module()
        # result has no 'memories' attribute at all
        mock_bank.fetch_memories.return_value = SimpleNamespace()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.fetch_memories(user_id="u1", query="q")
        assert result == []

    async def test_memory_without_fact_attr_falls_back_to_str(self):
        mock_mb, mock_bank = _make_mock_module()
        raw = object.__new__(object)  # plain object, no .fact
        mock_bank.fetch_memories.return_value = SimpleNamespace(memories=[raw])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.fetch_memories(user_id="u1", query="q")
        assert len(result) == 1
        assert isinstance(result[0], str)


# ── HermesMemoryBank.list_revisions ───────────────────────────────────────────

class TestListRevisions:

    async def test_returns_list_of_dicts(self):
        mock_mb, mock_bank = _make_mock_module()
        rev1 = SimpleNamespace(revision_id="r1", create_time="2024-01-01", memory_count=5)
        rev2 = SimpleNamespace(revision_id="r2", create_time="2024-01-02", memory_count=8)
        mock_bank.list_revisions.return_value = SimpleNamespace(revisions=[rev1, rev2])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.list_revisions(user_id="u1")
        assert len(result) == 2
        assert result[0] == {"revision_id": "r1", "create_time": "2024-01-01", "memory_count": 5}
        assert result[1] == {"revision_id": "r2", "create_time": "2024-01-02", "memory_count": 8}

    async def test_returns_empty_list_on_error(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.list_revisions.side_effect = Exception("quota exceeded")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.list_revisions(user_id="u1")
        assert result == []

    async def test_revisions_attribute_missing_returns_empty(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.list_revisions.return_value = SimpleNamespace()  # no .revisions
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.list_revisions(user_id="u1")
        assert result == []

    async def test_missing_fields_default_gracefully(self):
        mock_mb, mock_bank = _make_mock_module()
        rev = SimpleNamespace()  # no revision_id / create_time / memory_count
        mock_bank.list_revisions.return_value = SimpleNamespace(revisions=[rev])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.list_revisions(user_id="u1")
        assert result == [{"revision_id": "", "create_time": "", "memory_count": 0}]


# ── HermesMemoryBank.format_for_prompt ────────────────────────────────────────

class TestFormatForPrompt:

    async def test_returns_formatted_string_with_header(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.return_value = SimpleNamespace(
            memories=[_make_memory("Prefers Python"), _make_memory("Works in EMEA")]
        )
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.format_for_prompt(user_id="u1", query="context")
        assert result.startswith("## User Memory (long-term context)")
        assert "- Prefers Python" in result
        assert "- Works in EMEA" in result

    async def test_returns_empty_string_when_no_memories(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.return_value = SimpleNamespace(memories=[])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.format_for_prompt(user_id="u1", query="q")
        assert result == ""

    async def test_returns_empty_string_when_fetch_fails(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.fetch_memories.side_effect = Exception("error")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.format_for_prompt(user_id="u1", query="q")
        assert result == ""

    async def test_respects_max_tokens_budget(self):
        mock_mb, mock_bank = _make_mock_module()
        # Create memories where the second would exceed budget
        mem_a = "A" * 100
        mem_b = "B" * 100
        mock_bank.fetch_memories.return_value = SimpleNamespace(
            memories=[_make_memory(mem_a), _make_memory(mem_b)]
        )
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            # max_tokens=25 → char_budget = 100, exactly fits mem_a but not both
            result = await bank.format_for_prompt(user_id="u1", query="q", max_tokens=25)
        assert mem_a in result
        assert mem_b not in result


# ── build_memory_bank ─────────────────────────────────────────────────────────

class TestBuildMemoryBank:

    def test_returns_none_when_resource_name_not_set(self):
        mock_settings = SimpleNamespace(memory_bank_resource_name=None)
        with patch("memory.memory_bank._get_memory_bank_module"), \
             patch("memory.memory_bank.get_settings" if False else "config.get_settings",
                   return_value=mock_settings, create=True):
            # Patch config.get_settings inside the module's import
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
            memory_bank_resource_name="projects/p/locations/l/memoryBanks/b"
        )
        mock_mb = MagicMock()
        import config
        original = config.get_settings
        config.get_settings = lambda: mock_settings
        try:
            with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
                result = build_memory_bank()
        finally:
            config.get_settings = original
        assert isinstance(result, HermesMemoryBank)
        assert result._resource_name == "projects/p/locations/l/memoryBanks/b"

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
        mock_mb, _ = _make_mock_module()
        new_bank = MagicMock()
        new_bank.resource_name = "projects/p/memoryBanks/new"
        mock_mb.MemoryBank.create.return_value = new_bank
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            result = create_memory_bank(project="p", location="us-central1")
        assert result == "projects/p/memoryBanks/new"
        mock_mb.MemoryBank.create.assert_called_once()

    def test_handles_already_exists_by_listing(self):
        mock_mb, _ = _make_mock_module()
        mock_mb.MemoryBank.create.side_effect = Exception("already exists: resource conflict")
        existing = MagicMock()
        existing.display_name = "hermes-memory-bank"
        existing.resource_name = "projects/p/memoryBanks/existing"
        mock_mb.MemoryBank.list.return_value = [existing]
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            result = create_memory_bank(project="p", location="us-central1")
        assert result == "projects/p/memoryBanks/existing"
        mock_mb.MemoryBank.list.assert_called_once()

    def test_handles_conflict_keyword_by_listing(self):
        mock_mb, _ = _make_mock_module()
        mock_mb.MemoryBank.create.side_effect = Exception("409 conflict")
        existing = MagicMock()
        existing.display_name = "hermes-memory-bank"
        existing.resource_name = "projects/p/memoryBanks/conflict-existing"
        mock_mb.MemoryBank.list.return_value = [existing]
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            result = create_memory_bank(
                project="p", location="us-central1", display_name="hermes-memory-bank"
            )
        assert result == "projects/p/memoryBanks/conflict-existing"

    def test_reraises_non_conflict_exceptions(self):
        mock_mb, _ = _make_mock_module()
        mock_mb.MemoryBank.create.side_effect = Exception("permission denied")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            with pytest.raises(Exception, match="permission denied"):
                create_memory_bank(project="p", location="us-central1")

    def test_skips_non_matching_display_name_in_list(self):
        mock_mb, _ = _make_mock_module()
        mock_mb.MemoryBank.create.side_effect = Exception("already exists")
        other = MagicMock()
        other.display_name = "some-other-bank"
        other.resource_name = "projects/p/memoryBanks/other"
        mock_mb.MemoryBank.list.return_value = [other]
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            # No matching display_name → should raise original exception
            with pytest.raises(Exception, match="already exists"):
                create_memory_bank(
                    project="p", location="us-central1", display_name="hermes-memory-bank"
                )

    def test_uses_custom_display_name(self):
        mock_mb, _ = _make_mock_module()
        new_bank = MagicMock()
        new_bank.resource_name = "projects/p/memoryBanks/custom"
        mock_mb.MemoryBank.create.return_value = new_bank
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            result = create_memory_bank(
                project="p", location="us-central1", display_name="my-custom-bank"
            )
        assert result == "projects/p/memoryBanks/custom"
        call_kwargs = mock_mb.MemoryBank.create.call_args[1]
        assert call_kwargs["display_name"] == "my-custom-bank"


# ── HermesMemoryBank.generate_memories (wait_for_completion) ──────────────────

class TestGenerateMemoriesAsync:

    async def test_passes_wait_for_completion_false(self):
        mock_mb, mock_bank = _make_mock_module()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.generate_memories(user_id="u1", user_text="hi", agent_text="hello")
        call_kwargs = mock_bank.generate_memories.call_args[1]
        assert call_kwargs.get("wait_for_completion") is False


# ── HermesMemoryBank.ingest_events ────────────────────────────────────────────

class TestIngestEvents:

    async def test_calls_bank_ingest_events(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_mb.ConversationEvent = MagicMock(side_effect=lambda role, text: SimpleNamespace(role=role, text=text))
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.ingest_events(
                user_id="u1",
                events=[
                    {"role": "user", "text": "How do I reset VPN?"},
                    {"role": "agent", "text": "Go to Settings > VPN > Reset."},
                ],
            )
        mock_bank.ingest_events.assert_called_once()
        call_kwargs = mock_bank.ingest_events.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert len(call_kwargs["events"]) == 2

    async def test_falls_back_to_dict_when_no_conversation_event_class(self):
        mock_mb, mock_bank = _make_mock_module()
        # ConversationEvent not available on module
        del mock_mb.ConversationEvent
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            await bank.ingest_events(user_id="u1", events=[{"role": "user", "text": "hi"}])
        mock_bank.ingest_events.assert_called_once()

    async def test_exception_is_swallowed(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_mb.ConversationEvent = MagicMock(side_effect=AttributeError)
        mock_bank.ingest_events.side_effect = RuntimeError("sdk error")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            # Should not raise
            await bank.ingest_events(user_id="u1", events=[{"role": "user", "text": "hi"}])


# ── HermesMemoryBank.purge_memories ───────────────────────────────────────────

class TestPurgeMemories:

    async def test_calls_purge_with_force_true(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.purge_memories.return_value = SimpleNamespace(purge_count=5)
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            count = await bank.purge_memories(user_id="u1")
        assert count == 5
        call_kwargs = mock_bank.purge_memories.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert call_kwargs["force"] is True  # dry_run=False → force=True

    async def test_dry_run_passes_force_false(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.purge_memories.return_value = SimpleNamespace(purge_count=3)
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            count = await bank.purge_memories(user_id="u1", dry_run=True)
        assert count == 3
        call_kwargs = mock_bank.purge_memories.call_args[1]
        assert call_kwargs["force"] is False  # dry_run=True → force=False

    async def test_returns_zero_on_exception(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.purge_memories.side_effect = RuntimeError("quota error")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            count = await bank.purge_memories(user_id="u1")
        assert count == 0

    async def test_purge_count_attribute_missing_returns_zero(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.purge_memories.return_value = SimpleNamespace()  # no purge_count
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            count = await bank.purge_memories(user_id="u1")
        assert count == 0


# ── HermesMemoryBank.delete_memory ────────────────────────────────────────────

class TestDeleteMemory:

    async def test_calls_memories_delete(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.memories = MagicMock()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.delete_memory("projects/p/memoryBanks/b/memories/m1")
        assert result is True
        mock_bank.memories.delete.assert_called_once_with(name="projects/p/memoryBanks/b/memories/m1")

    async def test_returns_false_on_exception(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.memories = MagicMock()
        mock_bank.memories.delete.side_effect = RuntimeError("not found")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.delete_memory("projects/p/memoryBanks/b/memories/m1")
        assert result is False


# ── HermesMemoryBank.create_memory ────────────────────────────────────────────

class TestCreateMemory:

    async def test_calls_memories_create_and_returns_name(self):
        mock_mb, mock_bank = _make_mock_module()
        created = SimpleNamespace(name="projects/p/memoryBanks/b/memories/new")
        mock_bank.memories = MagicMock()
        mock_bank.memories.create.return_value = created
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.create_memory(user_id="u1", fact="User is based in HK")
        assert result == "projects/p/memoryBanks/b/memories/new"
        call_kwargs = mock_bank.memories.create.call_args[1]
        assert call_kwargs["scope"] == {"user_id": "u1"}
        assert call_kwargs["fact"] == "User is based in HK"

    async def test_returns_none_on_exception(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.memories = MagicMock()
        mock_bank.memories.create.side_effect = RuntimeError("sdk error")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.create_memory(user_id="u1", fact="some fact")
        assert result is None


# ── HermesMemoryBank.update_memory ────────────────────────────────────────────

class TestUpdateMemory:

    async def test_calls_memories_update(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.memories = MagicMock()
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.update_memory(
                memory_resource_name="projects/p/memoryBanks/b/memories/m1",
                new_fact="Updated fact",
            )
        assert result is True
        mock_bank.memories.update.assert_called_once_with(
            name="projects/p/memoryBanks/b/memories/m1",
            fact="Updated fact",
        )

    async def test_returns_false_on_exception(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.memories = MagicMock()
        mock_bank.memories.update.side_effect = RuntimeError("not found")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.update_memory("projects/p/.../m1", "fact")
        assert result is False


# ── HermesMemoryBank.retrieve_profiles ────────────────────────────────────────

class TestRetrieveProfiles:

    async def test_returns_profiles_with_facts(self):
        mock_mb, mock_bank = _make_mock_module()
        profile = SimpleNamespace(
            scope={"user_id": "u1"},
            facts=[SimpleNamespace(fact="Prefers Python"), SimpleNamespace(fact="Works in EMEA")],
        )
        mock_bank.retrieve_profiles.return_value = SimpleNamespace(profiles=[profile])
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.retrieve_profiles(user_id="u1")
        assert len(result) == 1
        assert result[0]["scope"] == {"user_id": "u1"}
        assert result[0]["facts"] == ["Prefers Python", "Works in EMEA"]

    async def test_returns_empty_on_exception(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.retrieve_profiles.side_effect = RuntimeError("unavailable")
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.retrieve_profiles(user_id="u1")
        assert result == []

    async def test_profiles_attribute_missing_returns_empty(self):
        mock_mb, mock_bank = _make_mock_module()
        mock_bank.retrieve_profiles.return_value = SimpleNamespace()  # no .profiles
        with patch("memory.memory_bank._get_memory_bank_module", return_value=mock_mb):
            bank = HermesMemoryBank(resource_name="projects/p/memoryBanks/b")
            result = await bank.retrieve_profiles(user_id="u1")
        assert result == []
