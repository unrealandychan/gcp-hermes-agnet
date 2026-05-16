"""
memory/memory_bank.py

Thin wrapper around Vertex AI Agent Platform's native VertexAiMemoryBank.

Responsibilities:
- generate_memories()  — distil a conversation turn into durable memories (async, fire-and-forget)
- ingest_events()      — stream events for automatic batched memory generation (production-grade)
- fetch_memories()     — retrieve relevant memories for a user at session start
- retrieve_profiles()  — retrieve structured user memory profile
- purge_memories()     — bulk-delete all memories for a user (powers DELETE /memories endpoint)
- delete_memory()      — delete a specific memory by resource name
- create_memory()      — directly write a memory fact (memory-as-a-tool pattern)
- update_memory()      — correct/update an existing memory fact
- list_revisions()     — inspect revision history for a memory resource
- format_for_prompt()  — fetch + format memories as a system prompt snippet
- create_or_get()      — ensure a MemoryBank resource exists (idempotent)

Design notes:
- VertexAiMemoryBank is the OFFICIAL long-term memory primitive for Gemini
  Enterprise Agent Platform. It replaces the previous RAG-upload hack used
  in skill_store.py / skill_learning.py for user-context memory.
- Human-authored skills (skills/*.md) are NOT moved here — they stay in the
  RAG corpus via SkillLoader because they are procedural knowledge, not
  per-user episodic memory.
- All blocking SDK calls are wrapped in asyncio.to_thread() so the event
  loop is never stalled under high concurrency.
- generate_memories() uses wait_for_completion=False for fire-and-forget async
  background generation — the agent never blocks waiting for memory writes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Lazy import guard ──────────────────────────────────────────────────────────
# vertexai.preview.memory_bank may not exist in older SDK versions.
# We import lazily so the rest of the codebase still loads during tests.

def _get_memory_bank_module():
    try:
        from vertexai.preview import memory_bank as _mb
        return _mb
    except ImportError as exc:
        raise ImportError(
            "VertexAiMemoryBank requires google-cloud-aiplatform>=1.112. "
            "Run: pip install 'google-cloud-aiplatform[agent_engines,adk]>=1.112'"
        ) from exc


# ── Public API ─────────────────────────────────────────────────────────────────

class HermesMemoryBank:
    """
    Application-level facade over VertexAiMemoryBank.

    Usage:
        bank = HermesMemoryBank(resource_name="projects/.../memoryBanks/...")
        await bank.generate_memories(user_id="u123", conversation_turn=turn)
        memories = await bank.fetch_memories(user_id="u123", query="VPN setup")
    """

    def __init__(self, resource_name: str) -> None:
        self._resource_name = resource_name
        self._bank: Any = None  # lazy-init on first use

    # ── Internal ───────────────────────────────────────────────────────────────

    def _ensure_bank(self) -> Any:
        if self._bank is None:
            mb = _get_memory_bank_module()
            self._bank = mb.MemoryBank(resource_name=self._resource_name)
        return self._bank

    # ── Public async methods ───────────────────────────────────────────────────

    async def generate_memories(
        self,
        user_id: str,
        user_text: str,
        agent_text: str,
        agent_name: str = "",
    ) -> None:
        """
        Distil a conversation turn into durable memories.

        Called from skill_learning_callback (fire-and-forget) after every agent turn.
        The SDK call is blocking — we wrap it in asyncio.to_thread.

        Args:
            user_id:    The authenticated user identifier.
            user_text:  The user's message text.
            agent_text: The agent's response text.
            agent_name: Optional agent name for metadata.
        """
        def _blocking() -> None:
            bank = self._ensure_bank()
            conversation = (
                f"User: {user_text}\n"
                f"Agent ({agent_name}): {agent_text}"
            ) if agent_name else (
                f"User: {user_text}\nAgent: {agent_text}"
            )
            bank.generate_memories(
                scope={"user_id": user_id},
                conversation=conversation,
                wait_for_completion=False,  # async background generation — don't block
            )

        try:
            await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: generated memories for user=%s", user_id)
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.generate_memories failed for user=%s", user_id)

    async def ingest_events(
        self,
        user_id: str,
        events: list[dict],
    ) -> None:
        """
        Stream conversation events to Memory Bank for automatic batched memory generation.

        More production-grade than generate_memories() — the SDK batches events
        and triggers memory generation automatically via IngestEvents RPC.

        Args:
            user_id: The authenticated user identifier.
            events:  List of event dicts with keys 'role' ('user'|'agent') and 'text'.

        Example:
            await bank.ingest_events(user_id="u1", events=[
                {"role": "user",  "text": "How do I reset my VPN?"},
                {"role": "agent", "text": "Go to Settings > VPN > Reset."},
            ])
        """
        def _blocking() -> None:
            bank = self._ensure_bank()
            # Build event objects expected by the SDK
            mb = _get_memory_bank_module()
            sdk_events = []
            for ev in events:
                role = ev.get("role", "user")
                text = ev.get("text", "")
                # Try to use the SDK's Event/ConversationEvent type if available,
                # otherwise pass as plain dict — SDK accepts both.
                try:
                    event_obj = mb.ConversationEvent(role=role, text=text)  # type: ignore[attr-defined]
                except AttributeError:
                    event_obj = {"role": role, "text": text}  # type: ignore[assignment]
                sdk_events.append(event_obj)
            bank.ingest_events(
                scope={"user_id": user_id},
                events=sdk_events,
            )

        try:
            await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: ingested %d events for user=%s", len(events), user_id)
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.ingest_events failed for user=%s", user_id)

    async def purge_memories(
        self,
        user_id: str,
        dry_run: bool = False,
    ) -> int:
        """
        Bulk-delete all memories for a user.

        Uses MemoryBankService.PurgeMemories with a user_id filter.
        This is the correct implementation for DELETE /memories/{user_id}.

        Args:
            user_id: The user whose memories to delete.
            dry_run: If True, returns count without deleting (default: False).

        Returns:
            Number of memories deleted (or that would be deleted on dry_run).
        """
        def _blocking() -> int:
            bank = self._ensure_bank()
            result = bank.purge_memories(
                scope={"user_id": user_id},
                force=not dry_run,  # force=False → dry run, force=True → actually delete
            )
            return getattr(result, "purge_count", 0)

        try:
            count = await asyncio.to_thread(_blocking)
            action = "Would delete" if dry_run else "Deleted"
            logger.info("MemoryBank: %s %d memories for user=%s", action, count, user_id)
            return count
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.purge_memories failed for user=%s", user_id)
            return 0

    async def delete_memory(self, memory_resource_name: str) -> bool:
        """
        Delete a specific memory by its resource name.

        Args:
            memory_resource_name: Full resource name, e.g.
                "projects/p/locations/l/memoryBanks/b/memories/m"

        Returns:
            True on success, False on failure.
        """
        def _blocking() -> None:
            bank = self._ensure_bank()
            bank.memories.delete(name=memory_resource_name)  # type: ignore[attr-defined]

        try:
            await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: deleted memory %s", memory_resource_name)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.delete_memory failed: %s", memory_resource_name)
            return False

    async def create_memory(
        self,
        user_id: str,
        fact: str,
    ) -> str | None:
        """
        Directly write a memory fact without LLM extraction/consolidation.

        Useful for the 'memory-as-a-tool' pattern where the agent explicitly
        decides what to remember, bypassing automatic extraction.

        Args:
            user_id: The user this memory belongs to.
            fact:    The plain-text fact to store.

        Returns:
            The new memory's resource name, or None on failure.
        """
        def _blocking() -> str | None:
            bank = self._ensure_bank()
            result = bank.memories.create(  # type: ignore[attr-defined]
                scope={"user_id": user_id},
                fact=fact,
            )
            return getattr(result, "name", None)

        try:
            name = await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: created memory for user=%s fact=%r", user_id, fact[:60])
            return name
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.create_memory failed for user=%s", user_id)
            return None

    async def update_memory(
        self,
        memory_resource_name: str,
        new_fact: str,
    ) -> bool:
        """
        Update an existing memory with a corrected fact.

        Args:
            memory_resource_name: Full resource name of the memory to update.
            new_fact: The corrected/updated fact text.

        Returns:
            True on success, False on failure.
        """
        def _blocking() -> None:
            bank = self._ensure_bank()
            bank.memories.update(  # type: ignore[attr-defined]
                name=memory_resource_name,
                fact=new_fact,
            )

        try:
            await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: updated memory %s", memory_resource_name)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.update_memory failed: %s", memory_resource_name)
            return False

    async def retrieve_profiles(
        self,
        user_id: str,
    ) -> list[dict]:
        """
        Retrieve structured memory profiles for a user.

        RetrieveProfiles returns a higher-level view than RetrieveMemories —
        facts are organised into a structured profile object per scope.

        Returns:
            List of profile dicts with keys 'scope' and 'facts'.
        """
        def _blocking() -> list[dict]:
            bank = self._ensure_bank()
            result = bank.retrieve_profiles(scope={"user_id": user_id})  # type: ignore[attr-defined]
            profiles = []
            for profile in getattr(result, "profiles", []):
                profiles.append({
                    "scope": getattr(profile, "scope", {"user_id": user_id}),
                    "facts": [
                        getattr(f, "fact", str(f))
                        for f in getattr(profile, "facts", [])
                    ],
                })
            return profiles

        try:
            return await asyncio.to_thread(_blocking)
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.retrieve_profiles failed for user=%s", user_id)
            return []

    async def fetch_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[str]:
        """
        Retrieve the most relevant memories for a user.

        Called at session start (PreloadMemoryTool) to inject user context
        into the system prompt.

        Returns:
            List of memory strings, ready for system prompt injection.
        """
        def _blocking() -> list[str]:
            bank = self._ensure_bank()
            result = bank.fetch_memories(
                scope={"user_id": user_id},
                query=query,
                top_k=top_k,
            )
            # result.memories is a list of Memory objects with .fact attribute
            return [
                getattr(m, "fact", str(m))
                for m in (getattr(result, "memories", []) or [])
            ]

        try:
            memories = await asyncio.to_thread(_blocking)
            logger.debug(
                "MemoryBank: fetched %d memories for user=%s query=%r",
                len(memories), user_id, query[:60],
            )
            return memories
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.fetch_memories failed for user=%s", user_id)
            return []

    async def list_revisions(self, user_id: str) -> list[dict]:
        """
        Return revision history for all memories belonging to a user.
        Useful for debugging and the DELETE /memories/{user_id} endpoint.
        """
        def _blocking() -> list[dict]:
            bank = self._ensure_bank()
            result = bank.list_revisions(scope={"user_id": user_id})
            revisions = []
            for rev in getattr(result, "revisions", []):
                revisions.append({
                    "revision_id": getattr(rev, "revision_id", ""),
                    "create_time": str(getattr(rev, "create_time", "")),
                    "memory_count": getattr(rev, "memory_count", 0),
                })
            return revisions

        try:
            return await asyncio.to_thread(_blocking)
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.list_revisions failed for user=%s", user_id)
            return []

    async def format_for_prompt(
        self,
        user_id: str,
        query: str,
        max_tokens: int = 800,
    ) -> str:
        """
        Fetch memories and format them as a system prompt snippet.

        Returns an empty string if no memories are found or MemoryBank is unavailable.
        The caller (gateway/main.py) injects this into the session system prompt.
        """
        memories = await self.fetch_memories(user_id=user_id, query=query)
        if not memories:
            return ""

        lines = ["## User Memory (long-term context)", ""]
        char_budget = max_tokens * 4  # ~4 chars/token
        used = 0
        for mem in memories:
            if used + len(mem) > char_budget:
                break
            lines.append(f"- {mem}")
            used += len(mem)

        return "\n".join(lines)


# ── Factory ────────────────────────────────────────────────────────────────────

def build_memory_bank() -> HermesMemoryBank | None:
    """
    Build a HermesMemoryBank from settings.

    Returns None if MEMORY_BANK_RESOURCE_NAME is not configured (graceful degradation).
    """
    try:
        from config import get_settings
        settings = get_settings()
        resource_name = getattr(settings, "memory_bank_resource_name", None)
        if not resource_name:
            logger.info("MEMORY_BANK_RESOURCE_NAME not set — MemoryBank disabled.")
            return None
        return HermesMemoryBank(resource_name=resource_name)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to build HermesMemoryBank.")
        return None


# ── Setup helper (used by setup_wizard.py) ────────────────────────────────────

def create_memory_bank(project: str, location: str, display_name: str = "hermes-memory-bank") -> str:
    """
    Create a new MemoryBank resource. Returns the resource name.
    Safe to call multiple times — returns existing resource if found.
    """
    mb = _get_memory_bank_module()
    try:
        # Try to create
        bank = mb.MemoryBank.create(
            display_name=display_name,
            description="Hermes Agent Platform — long-term user memory (VertexAiMemoryBank)",
        )
        resource_name: str = bank.resource_name
        logger.info("Created MemoryBank: %s", resource_name)
        return resource_name
    except Exception as exc:
        # If already exists, list and return the first match
        err_str = str(exc).lower()
        if "already exists" in err_str or "conflict" in err_str:
            banks = mb.MemoryBank.list()
            for b in banks:
                if b.display_name == display_name:
                    logger.info("MemoryBank already exists: %s", b.resource_name)
                    return b.resource_name
        raise
