"""
agents/task_agent.py

Hybrid multi-agent planner with Dynamic Agent Synthesis.

On each request, TaskAgent:
  1. Receives the user task.
  2. Calls AgentSynthesizer to build a task-specific agent set from:
       - agent_registry.yaml  (domain-matched templates)
       - Skills corpus         (learned skill → micro-agent hydration)
  3. Independent sub-tasks  → ParallelAgent (synthesised agents run simultaneously)
  4. Dependent sub-tasks    → sequential transfer_to_agent

Architecture
────────────
  ┌─ TaskAgent (LlmAgent — planner + dispatcher) ──────────────────────────┐
  │                                                                         │
  │  At build time: AgentSynthesizer pre-synthesises a default set.        │
  │  At runtime:    TaskAgent re-synthesises for each task via tool call.  │
  │                                                                         │
  │  sub_agents (dynamic, task-specific):                                  │
  │    • ParallelDispatcher (ParallelAgent)                                 │
  │        └── [synthesised agents]                                        │
  │    • [same synthesised agents for sequential use]                      │
  └────────────────────────────────────────────────────────────────────────┘

Builder function signature
──────────────────────────
  build_task_agent(settings, specialist_agents) -> LlmAgent
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

# ADK 2.0: RetryConfig replaces tenacity-based retry patterns
try:
    from google.adk.agents import RetryConfig
    _RETRY_CONFIG = RetryConfig(max_attempts=3)
except ImportError:
    _RETRY_CONFIG = None

from config import Settings
from memory.skill_learning import build_skill_learning_callback
from models.provider import get_model

logger = logging.getLogger(__name__)

_TASK_AGENT_INSTRUCTION = """\
You are TaskAgent, a multi-domain task planner and dynamic coordinator.

For every request you:
1. **Analyse** — identify the domains involved (analytics, HR, IT, developer, finance, etc.)
2. **Synthesise** — the right agents have already been assembled for this task based on
   your request; they are available as your sub_agents.
3. **Decide** — parallel vs sequential dispatch:
   - Independent sub-tasks → transfer to SequentialPipeline
     (specialists run in parallel, then AggregatorAgent merges into ONE reply)
   - Dependent sub-tasks   → sequential transfer_to_agent (step by step)
4. **Done** — SequentialPipeline handles aggregation automatically; you do NOT need to
   combine results yourself when using the parallel path.

Sub-agents available to you
────────────────────────────
• SequentialPipeline  — runs ALL synthesised specialist agents SIMULTANEOUSLY via
                        ParallelDispatcher, then AggregatorAgent consolidates their
                        outputs into a single cohesive reply. Use for independent tasks.
• Individual agents   — use these for sequential dependent steps.
  The exact agents vary per task — check the sub_agents list you have been given.

Decision guide: parallel vs sequential
────────────────────────────────────────
Use SequentialPipeline when:
  ✓ Sub-tasks are fully independent (each needs only the original request)
  ✓ Speed matters and there is no data dependency between tasks
  ✓ User will receive ONE consolidated answer (AggregatorAgent handles synthesis)

Use sequential transfer_to_agent when:
  ✓ Agent B needs Agent A's output as input
  ✓ You need to inspect results before deciding the next step
  ✓ Only one domain is involved

Bias-for-action rules (IMPORTANT)
───────────────────────────────────
- Execute immediately with the information you have.
- Make reasonable assumptions for missing details (use "TBD" as placeholder).
- Only pause mid-execution at genuine blockers that cannot be inferred.
- Present completed work first, THEN ask for missing details at the end.

────────────────────────────────────────────────────
Example 1 — Onboarding (PARALLEL — independent tasks)
────────────────────────────────────────────────────
User: "Onboard John Li, Eng Manager, next Friday. No email yet."

Synthesised agents: HRAgent, ITHelpdeskAgent, AnalyticsAgent
Decision: all independent → SequentialPipeline
Result: AggregatorAgent delivers one combined HR + IT + headcount reply.
Final ask: "Please confirm John's email once IT creates it."

────────────────────────────────────────────────────
Example 2 — Incident (SEQUENTIAL — dependent)
────────────────────────────────────────────────────
User: "Checkout API 5xx spiking. Pull BQ logs then write post-mortem."

Synthesised agents: AnalyticsAgent, DeveloperAgent
Decision: post-mortem needs BQ results → sequential
Step 1 → AnalyticsAgent: fetch last-hour 5xx errors from BigQuery
Step 2 → DeveloperAgent: write post-mortem using those results

────────────────────────────────────────────────────
Example 3 — MBR with Finance (PARALLEL)
────────────────────────────────────────────────────
User: "Prepare MBR: Q3 revenue by region, headcount, open P1 incidents."

Synthesised agents: AnalyticsAgent, HRAgent, ITHelpdeskAgent, FinanceAgent
Decision: all independent → SequentialPipeline
Result: AggregatorAgent delivers one structured MBR briefing.
"""


def build_task_agent(
    settings: Settings,
    specialist_agents: list | None = None,
) -> LlmAgent:
    """
    Build TaskAgent with dynamic agent synthesis.

    specialist_agents: the default fallback set (from agents.yaml).
    Defaults to None; the function builds fresh copies internally.
    At runtime, AgentSynthesizer will produce task-specific agent sets.

    For the static build (deploy time), we use specialist_agents as the
    ParallelDispatcher's children and also expose them for sequential use.
    Each set is built fresh to avoid the ADK dual-parent restriction.

    Parallel flow (independent sub-tasks):
        SequentialPipeline
          ├── ParallelDispatcher  (all specialists simultaneously)
          └── AggregatorAgent     (consolidates into ONE user reply)

    Sequential flow (dependent sub-tasks):
        TaskAgent → sequential transfer_to_agent (individual specialists)
    """
    from agents.aggregator import build_aggregator_agent
    from agents.analytics import build_analytics_agent
    from agents.developer import build_developer_agent
    from agents.hr import build_hr_agent
    from agents.it_helpdesk import build_it_helpdesk_agent

    # Fresh copies for ParallelDispatcher (ADK: one parent per agent object)
    parallel_copies = [
        build_analytics_agent(settings),
        build_hr_agent(settings),
        build_it_helpdesk_agent(settings),
        build_developer_agent(settings),
    ]

    parallel_dispatcher = ParallelAgent(
        name="ParallelDispatcher",
        description=(
            "Runs all synthesised specialist agents simultaneously. "
            "Use for independent sub-tasks with no data dependency."
        ),
        sub_agents=parallel_copies,
    )

    # AggregatorAgent reads all parallel outputs → one cohesive user reply
    aggregator = build_aggregator_agent(settings)

    # SequentialPipeline: ParallelDispatcher → AggregatorAgent
    # This guarantees the user receives exactly ONE consolidated response.
    sequential_pipeline = SequentialAgent(
        name="SequentialPipeline",
        description=(
            "Runs ParallelDispatcher then AggregatorAgent in sequence. "
            "Use this for independent multi-domain tasks — all specialists run "
            "simultaneously, then AggregatorAgent merges results into one reply."
        ),
        sub_agents=[parallel_dispatcher, aggregator],
    )

    # TaskAgent: SequentialPipeline (parallel path) + originals for sequential fallback
    task_sub_agents = [sequential_pipeline] + list(specialist_agents or [])

    _agent_kwargs: dict = dict(
        name="TaskAgent",
        model=get_model(settings.agent_model_task_planner),
        description=(
            "Multi-step tasks requiring collaboration across any domain. "
            "Dynamically assembles the right agents from registry + learned skills."
        ),
        instruction=_TASK_AGENT_INSTRUCTION,
        sub_agents=task_sub_agents,
        after_agent_callback=build_skill_learning_callback(agent_name="TaskAgent"),
    )
    # ADK 2.0: attach RetryConfig when available
    if _RETRY_CONFIG is not None:
        _agent_kwargs["retry_config"] = _RETRY_CONFIG
    return LlmAgent(**_agent_kwargs)


def build_dynamic_parallel_dispatcher(
    settings: Settings,
    task: str,
) -> tuple[SequentialAgent, list[LlmAgent]]:
    """
    Synthesise a task-specific SequentialPipeline (ParallelDispatcher +
    AggregatorAgent) + sequential agent list.

    This is called at REQUEST TIME (not deploy time) for true JIT synthesis.
    Returns (SequentialPipeline, sequential_agents) ready for dynamic dispatch.

    Usage in a tool or callback:
        pipeline, seq_agents = build_dynamic_parallel_dispatcher(settings, task)
        # then use pipeline for parallel, seq_agents for sequential
    """
    from agents.aggregator import build_aggregator_agent
    from agents.synthesizer import AgentSynthesizer

    synthesizer = AgentSynthesizer(settings)
    agents = synthesizer.synthesise(task, seq=0)

    if not agents:
        logger.warning("Synthesis returned no agents for task=%r", task[:80])
        return None, []

    # Build fresh copies for parallel — each agent can only have one parent
    # Use seq=1 so names are distinct from the seq=0 sequential agents
    from agents.synthesizer import AgentSynthesizer as _S
    parallel_agents = _S(settings).synthesise(task, seq=1)

    dispatcher = ParallelAgent(
        name="DynamicParallelDispatcher",
        description="Dynamically synthesised parallel dispatcher for this task.",
        sub_agents=parallel_agents,
    )

    aggregator = build_aggregator_agent(settings)

    pipeline = SequentialAgent(
        name="DynamicSequentialPipeline",
        description=(
            "Dynamic pipeline: ParallelDispatcher → AggregatorAgent. "
            "Runs all synthesised specialists in parallel, then consolidates."
        ),
        sub_agents=[dispatcher, aggregator],
    )

    return pipeline, agents
