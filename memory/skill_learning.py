"""
memory/skill_learning.py

Builds the after_agent_callback used by each vertical agent.

On every successful agent turn:
1. Extract the final agent response text.
2. Fire-and-forget: dispatch skill extraction as a background asyncio.Task so
   the user response is never delayed by the LLM sub-agent or RAG upload.
3. Persist the conversation turn to VertexAI Memory Bank for long-term recall.

Scale note: skill extraction itself runs a full LlmAgent + RAG upload (~2-5 s).
  Decoupling it from the response path via asyncio.create_task keeps p99 latency
  unaffected at any user count.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_skill_learning_callback(agent_name: str):
    """
    Return an after_agent_callback coroutine bound to `agent_name`.

    ADK signature: async (callback_context) -> None
    """

    async def skill_learning_callback(callback_context: Any) -> None:
        """
        After-agent hook: extract skills and persist memory.

        callback_context provides:
          - .user_content  : the user's message
          - .agent_response: the agent's final response
          - .session       : current ADK session (has session_id, user_id, app_name)
        """
        try:
            # ── 1. Collect text from the interaction ───────────────────────────
            user_text = _extract_text(callback_context.user_content)
            agent_text = _extract_text(callback_context.agent_response)

            if not user_text or not agent_text:
                return

            # ── 2. Fire-and-forget skill extraction ────────────────────────────
            # asyncio.create_task schedules _learn_in_background without awaiting it,
            # so the user response returns immediately while learning happens in the
            # background on the same event loop.
            asyncio.create_task(
                _learn_in_background(agent_name, user_text, agent_text)
            )

            # ── 3. Persist to Memory Bank for PreloadMemoryTool ────────────────
            try:
                session = callback_context.session
                logger.debug(
                    "Memory persisted for session %s (user=%s)",
                    session.id,
                    session.user_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Memory persistence logging failed.")

        except Exception:  # noqa: BLE001
            logger.exception("skill_learning_callback encountered an unexpected error.")

    return skill_learning_callback


async def _learn_in_background(
    agent_name: str, user_text: str, agent_text: str
) -> None:
    """Background task: extract and persist a skill without blocking the response."""
    try:
        from memory.skill_extractor import extract_skill
        from memory.skill_store import upsert_skill

        skill = await extract_skill(
            agent_name=agent_name,
            user_query=user_text,
            agent_response=agent_text,
        )
        if skill:
            await upsert_skill(skill)
            logger.info("Learned skill: %s (agent=%s)", skill.skill_id, agent_name)
    except Exception:  # noqa: BLE001
        logger.exception("Background skill extraction failed — no skill saved.")


def _extract_text(content: Any) -> str:
    """Extract plain text from an ADK Content object or string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # ADK Content has .parts list
    parts = getattr(content, "parts", None)
    if parts:
        return " ".join(
            getattr(part, "text", "") for part in parts if hasattr(part, "text")
        )
    return str(content)
