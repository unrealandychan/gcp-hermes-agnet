"""
memory/memory_bank.py

Thin wrapper around Vertex AI Agent Engine's native memory service.

Responsibilities:
- generate_memories()  — distil a conversation turn into durable memories (async, fire-and-forget)
- ingest_events()      — stream events for automatic batched memory generation (production-grade)
- fetch_memories()     — retrieve relevant memories for a user at session start
- retrieve_profiles()  — not supported in new API, returns [] for compatibility
- purge_memories()     — bulk-delete all memories for a user (powers DELETE /memories endpoint)
- delete_memory()      — delete a specific memory by resource name
- create_memory()      — directly write a memory fact (memory-as-a-tool pattern)
- update_memory()      — correct/update an existing memory fact
- list_revisions()     — not supported in new API, returns [] for compatibility
- format_for_prompt()  — fetch + format memories as a system prompt snippet
- create_or_get()      — ensure an AgentEngine resource exists (idempotent)

SDK Migration Notes (google-cloud-aiplatform >= 1.112 / vertexai >= 1.5):
- The old `vertexai.preview.memory_bank.MemoryBank` class no longer exists.
- In SDK >= 1.112, memories are managed through `vertexai.Client.agent_engines.memories.*`.
- `create_memory_bank()` now creates a lightweight AgentEngine resource (no agent code needed)
  and returns its resource name for use as MEMORY_BANK_RESOURCE_NAME.
- All memory operations use `vertexai.Client(...).agent_engines.memories.*` APIs.
- Design notes:
  - Human-authored skills (skills/*.md) stay in the RAG corpus via SkillLoader.
  - All blocking SDK calls are wrapped in asyncio.to_thread() to avoid stalling the event loop.
  - generate_memories() is fire-and-forget (does not block the agent response).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.genai.types import Content, Part

logger = logging.getLogger(__name__)


# ── Lazy client factory ────────────────────────────────────────────────────────

def _get_vertexai_client(project: str | None = None, location: str | None = None):
    """
    Return a vertexai.Client instance.

    Falls back to settings if project/location are not provided.
    Raises ImportError with a helpful message if the SDK is too old.
    """
    try:
        import vertexai  # noqa: F401 — needed for version check
    except ImportError as exc:
        raise ImportError(
            "VertexAiMemoryBank requires google-cloud-aiplatform>=1.112. "
            "Run: pip install 'google-cloud-aiplatform[agent_engines,adk]>=1.112'"
        ) from exc

    try:
        from vertexai import Client as VertexClient  # type: ignore[attr-defined]
    except ImportError as exc:
        raise ImportError(
            "vertexai.Client not found. "
            "Upgrade to google-cloud-aiplatform>=1.112: "
            "pip install 'google-cloud-aiplatform[agent_engines,adk]>=1.112'"
        ) from exc

    if project is None or location is None:
        try:
            from config import get_settings
            settings = get_settings()
            project = project or getattr(settings, "gcp_project_id", None)
            location = location or getattr(settings, "gcp_region", "us-central1")
        except Exception:
            pass

    return VertexClient(project=project, location=location or "us-central1")


# ── Public API ─────────────────────────────────────────────────────────────────

class HermesMemoryBank:
    """
    Application-level facade over Vertex AI Agent Engine memories.

    The ``resource_name`` is the full AgentEngine resource name, e.g.:
        projects/my-project/locations/us-central1/reasoningEngines/1234567890

    Usage:
        bank = HermesMemoryBank(resource_name="projects/.../reasoningEngines/...")
        await bank.generate_memories(user_id="u123", user_text=..., agent_text=...)
        memories = await bank.fetch_memories(user_id="u123", query="VPN setup")
    """

    def __init__(self, resource_name: str) -> None:
        self._resource_name = resource_name
        self._client: Any = None  # lazy-init on first use

    # ── Internal ───────────────────────────────────────────────────────────────

    def _ensure_client(self):
        if self._client is None:
            self._client = _get_vertexai_client()
        return self._client

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
            client = self._ensure_client()
            # Use Content/Part objects — the Vertex AI SDK uses strict Pydantic models
            # that reject plain dicts with extra_forbidden. Passing Content objects
            # satisfies the schema and avoids "Extra inputs are not permitted" errors.
            client.agent_engines.memories.generate(
                name=self._resource_name,
                scope={"user_id": user_id},
                direct_contents_source={
                    "events": [
                        Content(role="user", parts=[Part(text=user_text)]),
                        Content(role="model", parts=[Part(text=agent_text)]),
                    ]
                },
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
            events:  List of event dicts with keys 'role' ('user'|'agent'/'model') and 'text'.

        Example:
            await bank.ingest_events(user_id="u1", events=[
                {"role": "user",  "text": "How do I reset my VPN?"},
                {"role": "agent", "text": "Go to Settings > VPN > Reset."},
            ])
        """
        def _blocking() -> None:
            client = self._ensure_client()
            # Use Content/Part objects — plain dicts trigger extra_forbidden in strict SDK models
            sdk_events = []
            for ev in events:
                role = ev.get("role", "user")
                if role == "agent":
                    role = "model"
                text = ev.get("text", "")
                sdk_events.append(Content(role=role, parts=[Part(text=text)]))

            client.agent_engines.memories.ingest_events(
                name=self._resource_name,
                scope={"user_id": user_id},
                direct_contents_source={"events": sdk_events},
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

        Args:
            user_id: The user whose memories to delete.
            dry_run: If True, returns count without deleting (default: False).

        Returns:
            Number of memories deleted (or that would be deleted on dry_run).
        """
        def _blocking() -> int:
            client = self._ensure_client()
            # Count first for return value / dry_run
            memories = list(client.agent_engines.memories.list(
                name=self._resource_name,
                config={"filter": f'scope.user_id="{user_id}"'},
            ))
            count = len(memories)
            if not dry_run:
                client.agent_engines.memories.purge(
                    name=self._resource_name,
                    filter=f'scope.user_id="{user_id}"',
                    force=True,
                )
            return count

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
                "projects/p/locations/l/reasoningEngines/e/memories/m"

        Returns:
            True on success, False on failure.
        """
        def _blocking() -> None:
            client = self._ensure_client()
            client.agent_engines.memories.delete(name=memory_resource_name)

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
            client = self._ensure_client()
            result = client.agent_engines.memories.create(
                name=self._resource_name,
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
            client = self._ensure_client()
            client.agent_engines.memories.update(
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

    async def retrieve_profiles(self, user_id: str) -> list[dict]:
        """
        Retrieve structured memory profiles for a user.

        Note: RetrieveProfiles is not available in the AgentEngine memories API (SDK >= 1.112).
        Use fetch_memories() instead for retrieving relevant context.

        Returns:
            Empty list (not supported in current SDK version).
        """
        logger.debug(
            "MemoryBank.retrieve_profiles: not supported in SDK >= 1.112 — "
            "use fetch_memories() instead for user=%s", user_id
        )
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
            client = self._ensure_client()
            results = client.agent_engines.memories.retrieve(
                name=self._resource_name,
                scope={"user_id": user_id},
                similarity_search_params={"query": query, "top_k": top_k},
            )
            return [
                getattr(m, "fact", str(m))
                for m in results
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
        Return revision history for memories belonging to a user.

        Note: Memory revision history is not directly exposed in the AgentEngine API (SDK >= 1.112).
        Returns an empty list for backward compatibility.
        """
        logger.debug(
            "MemoryBank.list_revisions: not supported in SDK >= 1.112 for user=%s", user_id
        )
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

def create_memory_bank(
    project: str,
    location: str,
    display_name: str = "hermes-memory-bank",
) -> str:
    """
    Create a new AgentEngine resource to serve as the MemoryBank.
    Returns the resource name (stored in MEMORY_BANK_RESOURCE_NAME).

    Safe to call multiple times — returns existing resource if found.

    Migration note:
        In SDK >= 1.112, there is no standalone VertexAiMemoryBank resource class.
        Memories are associated with an AgentEngine. This function creates a
        lightweight AgentEngine (no agent code) dedicated to memory storage,
        which replaces the old `vertexai.preview.memory_bank.MemoryBank.create()` call.
    """
    client = _get_vertexai_client(project=project, location=location)

    def _engine_resource_name(engine) -> str | None:
        """
        Extract the resource name from an AgentEngine object.

        In SDK >= 1.112, AgentEngine wraps a ReasoningEngine proto:
          engine.api_resource.name  →  "projects/.../reasoningEngines/..."
        Older builds exposed it directly as engine.name.
        We try both to stay forward-compatible.
        """
        # Preferred: go through the underlying proto resource
        api_resource = getattr(engine, "api_resource", None)
        if api_resource is not None:
            name = getattr(api_resource, "name", None)
            if name:
                return name
        # Fallback: some older SDK versions surfaced .name directly
        return getattr(engine, "name", None)

    # Check if an engine with this display_name already exists
    try:
        for engine in client.agent_engines.list():
            api_resource = getattr(engine, "api_resource", None)
            eng_display = (
                getattr(api_resource, "display_name", None)
                if api_resource is not None
                else getattr(engine, "display_name", None)
            )
            if eng_display == display_name:
                resource_name: str = _engine_resource_name(engine)  # type: ignore[assignment]
                logger.info("AgentEngine (MemoryBank) already exists: %s", resource_name)
                return resource_name
    except Exception:
        pass  # list() might fail on first run — proceed to create

    # Create a new AgentEngine for memory storage (no agent code needed)
    engine = client.agent_engines.create(
        config={
            "display_name": display_name,
            "description": "Hermes Agent Platform — long-term user memory (AgentEngine MemoryBank)",
        }
    )
    resource_name = _engine_resource_name(engine)
    if not resource_name:
        raise RuntimeError(
            f"AgentEngine created but could not extract resource name from object: {engine!r}"
        )
    logger.info("Created AgentEngine (MemoryBank): %s", resource_name)
    return resource_name
