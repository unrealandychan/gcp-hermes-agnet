"""
memory/memcell_extractor.py

EverOS-inspired MemCell extractor — replaces the flat skill blob extraction
with a structured four-field memory unit (Episode + Facts + Foresight + Metadata).

Key innovations borrowed from EverOS/EverCore (arXiv:2601.02163):
  1. Episode in 3rd-person with coreferences resolved
  2. Atomic Facts optimised for BM25 retrieval (not narrative prose)
  3. Foresight with explicit validity intervals (passive memory decay)
  4. Memory type taxonomy (skill / preference / knowledge / task_pattern / etc.)

The extractor runs as a dedicated LlmAgent via InMemoryRunner, same pattern
as the existing SkillExtractor — fire-and-forget from after_agent_callback.
"""
from __future__ import annotations

import json
import logging
import re
import time

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part

from config import get_settings
from memory.memcell_models import Foresight, MemCell, MemoryType
from models.provider import get_model

logger = logging.getLogger(__name__)

# ── Extraction prompt ──────────────────────────────────────────────────────────

_MEMCELL_INSTRUCTION = """
You are a structured memory extraction specialist for an AI agent platform.

Your job: analyse a completed AI agent interaction (one user turn + agent response)
and extract a structured MemCell capturing durable knowledge worth remembering.

OUTPUT FORMAT — respond with ONLY a valid JSON object, no markdown fences, no commentary:

{
  "memory_type": "<one of: skill, preference, relationship, knowledge, task_pattern, core>",
  "episode": "<3rd-person narrative summary, 1-3 sentences, all pronouns resolved to names/roles>",
  "facts": ["<atomic verifiable fact 1>", "<atomic verifiable fact 2>", ...],
  "foresight": [
    {"inference": "<forward-looking prediction>", "valid_until": "<YYYY-MM-DD or null>"}
  ]
}

GUIDELINES:
- episode: Write in 3rd person ("The user asked...", "The HR agent explained..."). Resolve all
  pronouns. Be concise but complete. Capture the semantic core, not raw dialogue.
- facts: Each fact must be atomic (one claim per item), verifiable, and keyword-rich for search.
  Max 8 facts. Omit trivial or highly session-specific details.
- foresight: Only include genuine forward-looking inferences. Set valid_until if the inference
  has a natural expiry (e.g. an upcoming event). Use null for permanent facts/preferences.
  Leave foresight as [] if no meaningful prediction can be made.
- memory_type: Pick the best fit:
    skill        = repeatable multi-step procedure the agent followed
    preference   = user preference or style (communication, tool, process)
    relationship = relationship between entities (people, teams, systems)
    knowledge    = domain fact or policy the agent surfaced
    task_pattern = recurring task type with a known resolution pattern
    core         = fundamental user identity fact (name, role, location)

If the interaction contains no durable knowledge worth remembering, respond with exactly:
NO_MEMORY
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# ── Singleton extractor agent ──────────────────────────────────────────────────

_EXTRACTOR_AGENT: LlmAgent | None = None


def _get_extractor_agent() -> LlmAgent:
    global _EXTRACTOR_AGENT  # noqa: PLW0603
    if _EXTRACTOR_AGENT is None:
        settings = get_settings()
        _EXTRACTOR_AGENT = LlmAgent(
            name="MemCellExtractor",
            model=get_model(settings.agent_model_skill_extractor),
            description="Extracts structured MemCell memory units from agent interactions.",
            instruction=_MEMCELL_INSTRUCTION,
        )
    return _EXTRACTOR_AGENT


# ── Public API ─────────────────────────────────────────────────────────────────

async def extract_memcell(
    agent_name: str,
    user_id: str,
    user_query: str,
    agent_response: str,
) -> MemCell | None:
    """
    Run the MemCell extractor and return a structured MemCell, or None.

    Designed to be called fire-and-forget from after_agent_callback — same
    pattern as the existing extract_skill() function.

    Args:
        agent_name:     Name of the agent that handled the interaction.
        user_id:        User identifier for memory scoping.
        user_query:     The user's message text.
        agent_response: The agent's response text.

    Returns:
        MemCell if durable knowledge was found, None otherwise.
    """
    prompt = (
        f"AGENT: {agent_name}\n\n"
        f"USER:\n{user_query}\n\n"
        f"AGENT RESPONSE:\n{agent_response}"
    )

    runner = InMemoryRunner(agent=_get_extractor_agent(), app_name="memcell_extractor")
    session = await runner.session_service.create_session(
        app_name="memcell_extractor", user_id="system"
    )

    response_text = ""
    user_content = Content(role="user", parts=[Part(text=prompt)])
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=user_content,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if hasattr(part, "text"):
                    response_text += part.text

    response_text = response_text.strip()
    if not response_text or response_text == "NO_MEMORY":
        logger.debug("MemCellExtractor: no durable memory in this interaction.")
        return None

    return _parse_memcell(response_text, agent_name=agent_name, user_id=user_id)


def _parse_memcell(
    raw: str,
    agent_name: str,
    user_id: str,
) -> MemCell | None:
    """Parse raw LLM output into a MemCell. Returns None on parse failure."""
    match = _JSON_RE.search(raw)
    if not match:
        logger.warning("MemCellExtractor: non-JSON response: %s", raw[:200])
        return None

    try:
        data = json.loads(match.group())

        # Normalise memory_type — default to knowledge on unknown values
        raw_type = data.get("memory_type", "knowledge")
        try:
            memory_type = MemoryType(raw_type)
        except ValueError:
            logger.debug("MemCellExtractor: unknown memory_type %r — defaulting to knowledge", raw_type)
            memory_type = MemoryType.KNOWLEDGE

        # Parse foresight list
        foresight_data = data.get("foresight", [])
        if not isinstance(foresight_data, list):
            foresight_data = []
        foresight = []
        for f in foresight_data:
            if isinstance(f, dict) and "inference" in f:
                foresight.append(Foresight(**f))

        # Generate a stable ID: <agent>_<epoch_ms>
        memcell_id = f"{agent_name.lower()}_{int(time.time() * 1000)}"

        return MemCell(
            memcell_id=memcell_id,
            agent_name=agent_name,
            user_id=user_id,
            memory_type=memory_type,
            episode=data.get("episode", ""),
            facts=data.get("facts", []),
            foresight=foresight,
        )

    except Exception:  # noqa: BLE001
        logger.exception("MemCellExtractor: failed to parse MemCell JSON.")
        return None
