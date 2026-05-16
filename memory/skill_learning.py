"""
memory/skill_learning.py

Builds the after_agent_callback used by each vertical agent.

On every successful agent turn:
1. Extract the final agent response from session.events (last event with
   author == agent_name and is_final_response()).
2. Fire-and-forget: dispatch skill extraction as a background asyncio.Task.
3. Persist the conversation turn to VertexAiMemoryBank.

ADK after_agent_callback signature (verified from ADK source):
    async def callback(*, callback_context: CallbackContext) -> None

CallbackContext provides:
    .user_content   — the user's Content object (parts with .text)
    .session        — Session object with .events list and .user_id
    .agent_name     — name of the agent that just completed
    .state          — session state dict

Agent response is recovered from session.events: the last Event where
    event.author == agent_name and event.is_final_response() == True.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_skill_learning_callback(agent_name: str):
    """
    Return an after_agent_callback coroutine bound to `agent_name`.

    ADK verified signature: async (*, callback_context) -> None
    """

    async def skill_learning_callback(*, callback_context: Any) -> None:
        try:
            # ── 1. Extract user text from CallbackContext.user_content ─────────
            user_text = _extract_text(callback_context.user_content)

            # ── 2. Extract agent text from session.events ─────────────────────
            # CallbackContext has no agent_response field — the agent's final
            # reply lives in session.events as the last Event authored by this
            # agent where is_final_response() is True.
            agent_text = _extract_agent_response(
                callback_context.session, agent_name
            )

            logger.debug(
                "skill_learning_callback fired: agent=%s user=%r agent=%r",
                agent_name,
                user_text[:80] if user_text else None,
                agent_text[:80] if agent_text else None,
            )

            if not user_text or not agent_text:
                logger.debug(
                    "skill_learning_callback: skipping — empty user_text or agent_text"
                )
                return

            # ── 3. Fire-and-forget skill extraction ───────────────────────────
            asyncio.create_task(
                _learn_in_background(agent_name, user_text, agent_text)
            )

            # ── 4. Fire-and-forget memory persistence ─────────────────────────
            asyncio.create_task(
                _persist_to_memory_bank(
                    agent_name=agent_name,
                    user_text=user_text,
                    agent_text=agent_text,
                    callback_context=callback_context,
                )
            )

        except Exception:  # noqa: BLE001
            logger.exception("skill_learning_callback encountered an unexpected error.")

    return skill_learning_callback


def _extract_agent_response(session: Any, agent_name: str) -> str:
    """
    Walk session.events in reverse to find the last final response from agent_name.

    Event fields (verified):
        .author            — str, name of the agent/model that produced this event
        .is_final_response() — bool method
        .content           — Optional[Content] with .parts list
    """
    events = getattr(session, "events", None) or []
    for event in reversed(events):
        author = getattr(event, "author", None)
        if author != agent_name:
            continue
        try:
            is_final = event.is_final_response()
        except Exception:
            is_final = False
        if not is_final:
            continue
        text = _extract_text(getattr(event, "content", None))
        if text:
            return text
    return ""


async def _persist_to_memory_bank(
    agent_name: str,
    user_text: str,
    agent_text: str,
    callback_context: Any,
) -> None:
    """Write this conversation turn to the native VertexAiMemoryBank."""
    try:
        from memory.memory_bank import build_memory_bank
        bank = build_memory_bank()
        if bank is None:
            return
        user_id = getattr(callback_context, "user_id", None) or getattr(
            callback_context.session, "user_id", "anonymous"
        )
        await bank.generate_memories(
            user_id=user_id,
            user_text=user_text,
            agent_text=agent_text,
            agent_name=agent_name,
        )
    except Exception:  # noqa: BLE001
        logger.exception("MemoryBank persistence failed — no memory written.")


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
    parts = getattr(content, "parts", None)
    if parts:
        return " ".join(
            getattr(part, "text", "") for part in parts if hasattr(part, "text")
        ).strip()
    return str(content)
