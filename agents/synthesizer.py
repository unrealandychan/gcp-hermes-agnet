"""
agents/synthesizer.py

AgentSynthesizer — Dynamic Agent Synthesis engine.

Given a task description, synthesises the optimal set of agents by:

  1. Registry lookup  — scan agent_registry.yaml for domain-matching templates
  2. Skill retrieval  — search the skills corpus for learned procedures
  3. Skill hydration  — materialise each matching skill into an ephemeral
                        micro-agent with a procedure-aware instruction
  4. Deduplication    — merge registry agents + skill agents, prefer richer
                        skill-hydrated version when both cover the same domain
  5. Return           — list[LlmAgent] ready for ParallelAgent or sequential use

The synthesizer deliberately avoids a second LLM call for agent selection:
domain-keyword scoring is fast, deterministic, and cheap.  An LLM reranking
pass can be added later if needed.

Usage
─────
    from agents.synthesizer import AgentSynthesizer

    synthesizer = AgentSynthesizer(settings)
    agents = synthesizer.synthesise(task="Help onboard John Li as Eng Manager")
    # returns e.g. [HRAgent, ITHelpdeskAgent, AnalyticsAgent]
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import yaml
from google.adk.agents import LlmAgent

from config import Settings
from memory.skill_models import Skill
from memory.skill_store import search_skills
from models.provider import get_model
from agents.loader import build_tool_map

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent.parent / "agent_registry.yaml"

# Maximum agents to synthesise per task (keep context manageable)
_MAX_AGENTS = 6
# Minimum keyword overlap score to include a registry template
_MIN_SCORE = 1


def _unique_suffix(task: str, seq: int = 0) -> str:
    """
    Return a short deterministic suffix derived from *task* + sequence number.

    Format: ``_<4-char-hex>_<seq>``  e.g.  ``_a3f1_0``

    Using a hash of the task keeps names stable across restarts (same task →
    same suffix), while the sequence number distinguishes parallel copies
    synthesised within a single task run (ADK dual-parent rule).
    """
    digest = hashlib.sha1(task.encode()).hexdigest()[:4]  # noqa: S324 – not security
    return f"_{digest}_{seq}"


def unique_agent_name(base_name: str, task: str, seq: int = 0) -> str:
    """
    Return a globally unique agent name for *base_name* within *task*.

    >>> unique_agent_name("AnalyticsAgent", "analyse revenue", seq=0)
    'AnalyticsAgent_3c2a_0'
    """
    return base_name + _unique_suffix(task, seq)


class AgentSynthesizer:
    """
    Synthesises a task-specific agent set from registry templates + learned skills.

    Args:
        settings: Application Settings (model config, corpus names).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._registry = self._load_registry()
        self._tool_map = build_tool_map(settings)

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesise(self, task: str, seq: int = 0) -> list[LlmAgent]:
        """
        Return a deduplicated list of LlmAgents best suited for `task`.

        Args:
            task: Natural-language task description.
            seq:  Sequence counter — increment when building a second copy of
                  the same task's agents (ADK dual-parent rule).  Agents from
                  seq=0 and seq=1 have distinct names even for the same task.

        Steps:
          1. Score registry templates against task keywords.
          2. Retrieve matching skills from corpus.
          3. Hydrate skills into micro-agents.
          4. Merge, deduplicate, cap at _MAX_AGENTS.
        """
        self._current_task = task  # stored so sub-methods can access it
        self._current_seq = seq
        task_tokens = _tokenise(task)

        # Step 1 — Registry candidates
        registry_candidates = self._score_registry(task_tokens)

        # Step 2 & 3 — Skill candidates
        skill_agents = self._synthesise_from_skills(task)

        # Step 4 — Merge: skill-agents take precedence (richer instruction)
        merged = self._merge(registry_candidates, skill_agents)

        if not merged:
            logger.warning(
                "AgentSynthesizer: no agents matched task=%r — "
                "falling back to core registry agents",
                task[:120],
            )
            merged = self._fallback_core_agents()

        logger.info(
            "AgentSynthesizer: synthesised %d agent(s) for task=%r: %s",
            len(merged),
            task[:80],
            [a.name for a in merged],
        )
        return merged

    # ── Registry ──────────────────────────────────────────────────────────────

    def _load_registry(self) -> list[dict]:
        if not _REGISTRY_PATH.exists():
            logger.warning("agent_registry.yaml not found at %s", _REGISTRY_PATH)
            return []
        with _REGISTRY_PATH.open() as f:
            data = yaml.safe_load(f)
        return data.get("templates", [])

    def _score_registry(self, task_tokens: set[str]) -> list[LlmAgent]:
        """Score each template by keyword overlap; return sorted list."""
        scored: list[tuple[int, int, dict]] = []
        for tmpl in self._registry:
            domain_tokens = set(
                kw.lower().replace("&", "").replace("-", "_")
                for kw in (tmpl.get("domain") or [])
            )
            score = len(task_tokens & domain_tokens)
            if score >= _MIN_SCORE:
                priority = tmpl.get("priority", 2)
                scored.append((score, -priority, tmpl))

        # Sort: higher score first, then lower priority number first
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        agents = []
        for score, _, tmpl in scored[: _MAX_AGENTS]:
            agent = self._build_from_template(tmpl)
            if agent:
                agents.append(agent)
        return agents

    def _build_from_template(self, tmpl: dict) -> LlmAgent | None:
        """Instantiate an LlmAgent from a registry template dict."""
        try:
            tool_names: list[str] = tmpl.get("tools") or []
            tools = [
                self._tool_map[t]
                for t in tool_names
                if t in self._tool_map
            ]
            model_name = tmpl.get("model") or self._settings.agent_model_default
            base_name = tmpl["name"]
            task = getattr(self, "_current_task", "")
            seq = getattr(self, "_current_seq", 0)
            agent_name = unique_agent_name(base_name, task, seq) if task else base_name
            return LlmAgent(
                name=agent_name,
                model=get_model(model_name),
                description=tmpl.get("description", ""),
                instruction=tmpl.get("instruction", "You are a helpful assistant."),
                tools=tools,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to build agent from template: %s", tmpl.get("name"))
            return None

    # ── Skill hydration ───────────────────────────────────────────────────────

    def _synthesise_from_skills(self, task: str) -> list[LlmAgent]:
        """Search skills corpus and materialise matching skills as micro-agents."""
        try:
            skills = search_skills(task, top_k=_MAX_AGENTS)
        except Exception:  # noqa: BLE001
            logger.exception("Skill retrieval failed — skipping skill hydration.")
            return []

        agents = []
        for skill in skills:
            agent = self._hydrate_skill(skill)
            if agent:
                agents.append(agent)
        return agents

    def _hydrate_skill(self, skill: Skill) -> LlmAgent | None:
        """
        Turn a Skill into an ephemeral LlmAgent with a procedure-aware instruction.

        The agent name is derived from the skill so it doesn't clash with
        static registry agents:  e.g.  "Skill_analytics_bq_revenue_query"
        """
        try:
            # Derive a safe agent name from skill_id, scoped to current task
            base_name = "Skill_" + re.sub(r"[^a-zA-Z0-9_]", "_", skill.skill_id)[:48]
            task = getattr(self, "_current_task", "")
            seq = getattr(self, "_current_seq", 0)
            agent_name = unique_agent_name(base_name, task, seq) if task else base_name

            procedure_text = "\n".join(
                f"  {i + 1}. {step}"
                for i, step in enumerate(skill.procedure)
            )
            instruction = (
                f"You are a specialist agent synthesised from a learned skill.\n\n"
                f"SKILL: {skill.skill_id}\n"
                f"DOMAIN: {skill.domain}\n"
                f"TRIGGER: {skill.trigger}\n\n"
                f"PROCEDURE — follow these steps exactly:\n{procedure_text}\n\n"
                f"Apply this procedure to the user's request. "
                f"If the request doesn't match, say so clearly."
            )

            # Infer tools from skill domain keyword
            tool_names = self._infer_tools_for_domain(skill.domain)
            tools = [self._tool_map[t] for t in tool_names if t in self._tool_map]

            return LlmAgent(
                name=agent_name,
                model=get_model(self._settings.agent_model_default),
                description=(
                    f"Skill-materialised agent: {skill.trigger} "
                    f"(domain={skill.domain})"
                ),
                instruction=instruction,
                tools=tools,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to hydrate skill: %s", skill.skill_id)
            return None

    def _infer_tools_for_domain(self, domain: str) -> list[str]:
        """Map a domain string to a sensible default tool list."""
        domain = domain.lower()
        if any(k in domain for k in ("analytics", "data", "sql", "bigquery")):
            return ["bigquery", "search"]
        if any(k in domain for k in ("code", "developer", "debug", "infra")):
            return ["search", "code_sandbox"]
        if any(k in domain for k in ("hr", "policy", "onboard")):
            return ["search", "rag_knowledge"]
        if any(k in domain for k in ("it", "helpdesk", "incident", "security")):
            return ["search", "rag_knowledge"]
        return ["search"]

    # ── Merge & dedup ─────────────────────────────────────────────────────────

    def _merge(
        self,
        registry_agents: list[LlmAgent],
        skill_agents: list[LlmAgent],
    ) -> list[LlmAgent]:
        """
        Merge registry + skill agents. Skill agents take precedence for
        their domain (richer, task-specific instruction).
        Caps total at _MAX_AGENTS.
        """
        seen_names: set[str] = set()
        merged: list[LlmAgent] = []

        # Skill agents first (higher specificity)
        for agent in skill_agents:
            if agent.name not in seen_names:
                merged.append(agent)
                seen_names.add(agent.name)

        # Registry agents fill remaining slots
        for agent in registry_agents:
            if agent.name not in seen_names:
                merged.append(agent)
                seen_names.add(agent.name)

        return merged[:_MAX_AGENTS]

    def _fallback_core_agents(self) -> list[LlmAgent]:
        """Return priority-1 registry agents as a safe fallback."""
        core = [t for t in self._registry if t.get("priority", 2) == 1]
        agents = []
        for tmpl in core[:4]:
            agent = self._build_from_template(tmpl)
            if agent:
                agents.append(agent)
        return agents


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokenise(text: str) -> set[str]:
    """Lowercase word tokens from text, normalised for domain matching."""
    return {
        re.sub(r"[^a-z0-9_]", "", w)
        for w in text.lower().split()
        if len(w) > 2
    }
