"""
memory/memory_bank.py

Thin wrapper around Vertex AI Agent Platform's native VertexAiMemoryBank.

Responsibilities:
- generate_memories()  — distil a conversation turn into durable memories
- fetch_memories()     — retrieve relevant memories for a user at session start
- list_revisions()     — inspect revision history for a memory resource
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
            )

        try:
            await asyncio.to_thread(_blocking)
            logger.debug("MemoryBank: generated memories for user=%s", user_id)
        except Exception:  # noqa: BLE001
            logger.exception("MemoryBank.generate_memories failed for user=%s", user_id)

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
