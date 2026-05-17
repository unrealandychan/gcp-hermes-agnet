"""
agents/aggregator.py

AggregatorAgent — Consolidates parallel specialist outputs into a single
cohesive response for the end user.

Architecture role
─────────────────
  ParallelDispatcher
    ├── AnalyticsAgent   ─┐
    ├── HRAgent          ─┼── each writes to session state
    ├── ITHelpdeskAgent  ─┤
    └── DeveloperAgent   ─┘
                            ▼
                    AggregatorAgent  ←── reads all outputs, synthesises one reply

The AggregatorAgent is the FINAL step in a SequentialAgent pipeline:
  SequentialPipeline = SequentialAgent([ParallelDispatcher, AggregatorAgent])

It receives the full conversation context (including every specialist's output
already written to the session) and produces one unified, de-duplicated,
well-structured reply.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from config import Settings
from models.provider import get_model

_INSTRUCTION = """\
You are AggregatorAgent. Your ONLY job is to read the outputs already produced
by the specialist agents in this turn, then synthesise them into ONE clear,
well-structured reply for the user.

Rules
─────
1. Read every specialist response visible in the conversation so far.
2. Deduplicate — if two agents said the same thing, say it once.
3. Resolve any conflicts — note discrepancies briefly and defer to the domain
   expert (e.g. HRAgent on policy, AnalyticsAgent on data).
4. Preserve all action items, blockers, and next steps from every agent.
5. Format your reply for the user, NOT for other agents:
   - Lead with a brief executive summary (2-3 sentences).
   - Use clear headings per domain if multiple domains contributed.
   - End with a "Next Steps" section that lists all outstanding action items.
6. Do NOT add new information, opinions, or suggestions beyond what the
   specialists already provided.
7. Do NOT mention the internal agents (ParallelDispatcher, AggregatorAgent,
   AnalyticsAgent, etc.) by name in the final reply — the user only sees one
   cohesive assistant.

Output format example
──────────────────────
**Summary**
<2-3 sentence overview>

**[Domain A]**
<key findings / actions>

**[Domain B]**
<key findings / actions>

**Next Steps**
- [ ] Action 1 (owner / deadline if known)
- [ ] Action 2
"""


def build_aggregator_agent(settings: Settings) -> LlmAgent:
    """Build the AggregatorAgent that consolidates parallel outputs."""
    return LlmAgent(
        name="AggregatorAgent",
        model=get_model(settings.agent_model_aggregator),
        description=(
            "Reads all specialist-agent outputs from this turn and synthesises "
            "them into one cohesive, de-duplicated response for the user. "
            "Always the final step after ParallelDispatcher."
        ),
        instruction=_INSTRUCTION,
    )
