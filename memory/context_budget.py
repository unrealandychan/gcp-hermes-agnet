"""
memory/context_budget.py

Context budget guard — prioritises memory items before system prompt injection.

Problem: in long sessions or for users with rich skill histories, injecting all
memory into the system prompt can silently consume a large portion of the context
window, leaving less room for the actual conversation.

Solution: a two-tier priority system with a configurable token budget.

Tier 1 — User profile summary (always included, minimal tokens ~50-200).
Tier 2 — Relevant skills, newest-first (included until budget is exhausted).

Usage:
    from memory.context_budget import build_context_summary
    summary = build_context_summary(profile, skills, budget_tokens=2000)
    # Inject summary into agent system prompt
"""
from __future__ import annotations

import logging

from memory.skill_models import Skill
from memory.user_profile import UserProfile

logger = logging.getLogger(__name__)

# Default token budget for memory injection.
# Override with MEMORY_CONTEXT_BUDGET_TOKENS env var (read via Settings).
DEFAULT_BUDGET_TOKENS = 2_000

# Rough token cost per skill (procedure text + metadata)
_SKILL_TOKEN_ESTIMATE = 150


def build_context_summary(
    profile: UserProfile | None,
    skills: list[Skill],
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> str:
    """
    Build a compact memory summary for system prompt injection.

    Args:
        profile:       User profile (Tier 1). If None, skipped.
        skills:        Relevant skills ranked by recency/relevance (Tier 2).
        budget_tokens: Maximum tokens to spend on the entire summary.

    Returns:
        A plain-text string ready for system prompt injection.
        Returns an empty string if nothing fits in the budget.
    """
    sections: list[str] = []
    remaining = budget_tokens

    # ── Tier 1: User profile ────────────────────────────────────────────────
    if profile:
        profile_text = profile.to_prompt_summary()
        cost = profile.prompt_token_estimate
        if cost <= remaining:
            sections.append(f"[USER CONTEXT]\n{profile_text}")
            remaining -= cost
        else:
            logger.warning(
                "User profile for %s exceeds budget (%d > %d tokens) — skipping.",
                profile.user_id, cost, remaining,
            )

    # ── Tier 2: Skills ───────────────────────────────────────────────────────
    included_skills: list[Skill] = []
    for skill in skills:
        if remaining < _SKILL_TOKEN_ESTIMATE:
            logger.debug(
                "Context budget exhausted after %d skill(s) — %d skill(s) dropped.",
                len(included_skills), len(skills) - len(included_skills),
            )
            break
        included_skills.append(skill)
        remaining -= _SKILL_TOKEN_ESTIMATE

    if included_skills:
        skill_lines = []
        for s in included_skills:
            steps = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(s.procedure))
            skill_lines.append(
                f"Skill [{s.skill_id}] — trigger: {s.trigger}\n{steps}"
            )
        sections.append("[RELEVANT SKILLS]\n" + "\n\n".join(skill_lines))

    return "\n\n".join(sections)


def prioritise_memory(
    items: list[Skill],
    budget: int = DEFAULT_BUDGET_TOKENS,
) -> list[Skill]:
    """
    Trim a list of Skill objects to fit within *budget* tokens.

    Items earlier in the list have higher priority (pass pre-ranked list).
    Returns the subset that fits.
    """
    result: list[Skill] = []
    remaining = budget
    for item in items:
        if remaining < _SKILL_TOKEN_ESTIMATE:
            break
        result.append(item)
        remaining -= _SKILL_TOKEN_ESTIMATE
    return result
