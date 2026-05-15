"""
memory/skill_extractor.py

Uses a dedicated LlmAgent to extract a structured Skill from a completed
agent interaction (user query + agent response).

Returns a Skill object, or None if no reusable procedure was found.
"""
from __future__ import annotations

import json
import logging
import re

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner

from config import get_settings
from memory.skill_models import Skill
from models.provider import get_model

logger = logging.getLogger(__name__)

_EXTRACTOR_INSTRUCTION = """
You are a skill extraction specialist. You analyse a completed AI agent interaction
and decide whether it contains a reusable procedure worth saving as a skill.

A skill is worth saving if:
- The agent followed a clear, repeatable multi-step process.
- The same query type could occur again.
- The procedure is specific enough to be actionable.

If a skill is worth saving, respond with ONLY a valid JSON object (no markdown,
no commentary) matching this schema:
{
  "skill_id": "<agent_name_snake>_<2-4 word slug>",
  "agent_name": "<agent_name>",
  "domain": "<domain tag>",
  "trigger": "<one sentence: when to apply this skill>",
  "procedure": ["step 1", "step 2", ...],
  "example_query": "<the user query from the interaction>"
}

If no skill is worth saving, respond with exactly: NO_SKILL
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _build_extractor_agent() -> LlmAgent:
    """Build the SkillExtractor agent using the configured lightweight model."""
    settings = get_settings()
    return LlmAgent(
        name="SkillExtractor",
        model=get_model(settings.agent_model_skill_extractor),
        description="Extracts reusable skills from agent interactions.",
        instruction=_EXTRACTOR_INSTRUCTION,
    )


# Singleton — built once per process, respects settings at startup time.
_EXTRACTOR_AGENT: LlmAgent | None = None


def _get_extractor_agent() -> LlmAgent:
    global _EXTRACTOR_AGENT  # noqa: PLW0603
    if _EXTRACTOR_AGENT is None:
        _EXTRACTOR_AGENT = _build_extractor_agent()
    return _EXTRACTOR_AGENT


async def extract_skill(
    agent_name: str,
    user_query: str,
    agent_response: str,
) -> Skill | None:
    """
    Run the extractor agent and parse the result.

    Returns a Skill if one was extracted, None otherwise.
    """
    prompt = (
        f"AGENT: {agent_name}\n\n"
        f"USER QUERY:\n{user_query}\n\n"
        f"AGENT RESPONSE:\n{agent_response}"
    )

    runner = InMemoryRunner(agent=_get_extractor_agent(), app_name="skill_extractor")
    session = await runner.session_service.create_session(
        app_name="skill_extractor", user_id="system"
    )
    response_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=prompt,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if hasattr(part, "text"):
                    response_text += part.text

    response_text = response_text.strip()
    if not response_text or response_text == "NO_SKILL":
        return None

    match = _JSON_RE.search(response_text)
    if not match:
        logger.warning("SkillExtractor returned non-JSON: %s", response_text[:200])
        return None

    try:
        data = json.loads(match.group())
        data["agent_name"] = agent_name  # enforce correct agent name
        return Skill(**data)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to parse extracted skill JSON.")
        return None
