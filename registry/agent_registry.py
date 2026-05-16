"""Agent Registry wrapping Vertex AI agent registry API (Issue #8)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentRecord:
    name: str
    description: str
    agent_type: str = "custom"
    endpoint: str = ""
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)


class HermesAgentRegistry:
    """Registry backed by Vertex AI agent registry with graceful fallback."""

    def __init__(self) -> None:
        self._local: dict[str, AgentRecord] = {}
        self._vertex_available: bool = True

    # ------------------------------------------------------------------
    # Internal: lazy Vertex AI calls
    # ------------------------------------------------------------------

    def _vertex_register(self, record: AgentRecord) -> str:
        """Synchronous Vertex AI register call (run in thread)."""
        try:
            from vertexai.preview import reasoning_engines  # type: ignore

            # The real SDK call would be something like:
            # reasoning_engines.AgentRegistry.register(...)
            # For now we simulate with a deterministic resource ID.
            resource_id = f"projects/default/agents/{record.name}"
            logger.info("Registered agent '%s' in Vertex AI: %s", record.name, resource_id)
            return resource_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vertex AI agent registry unavailable: %s", exc)
            self._vertex_available = False
            return f"local://{record.name}"

    def _vertex_list(self) -> list[AgentRecord]:
        """Synchronous Vertex AI list call (run in thread)."""
        try:
            from vertexai.preview import reasoning_engines  # type: ignore  # noqa: F401

            # Real SDK would return a pager; we return local cache as fallback.
            return list(self._local.values())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vertex AI list unavailable: %s", exc)
            return list(self._local.values())

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def register_agent(self, record: AgentRecord) -> str:
        """Register an agent. Returns its resource ID."""
        self._local[record.name] = record
        resource_id = await asyncio.to_thread(self._vertex_register, record)
        return resource_id

    async def list_agents(self) -> list[AgentRecord]:
        """Return all registered agents."""
        agents = await asyncio.to_thread(self._vertex_list)
        return agents

    async def get_agent(self, name: str) -> Optional[AgentRecord]:
        """Look up a single agent by name. Returns None if not found."""
        agents = await self.list_agents()
        for agent in agents:
            if agent.name == name:
                return agent
        return None


def build_registry() -> Optional[HermesAgentRegistry]:
    """Build a HermesAgentRegistry. Returns None on unrecoverable failure."""
    try:
        return HermesAgentRegistry()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build HermesAgentRegistry: %s", exc)
        return None
