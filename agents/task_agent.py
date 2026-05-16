"""
agents/task_agent.py

Hybrid multi-agent planner — decomposes tasks and dispatches them either:
  • In PARALLEL (ParallelDispatcher) for independent sub-tasks that don't
    depend on each other's results (e.g. HR policy + IT setup + headcount).
  • In SEQUENCE (transfer_to_agent) for dependent sub-tasks where step N
    needs the result of step N-1 (e.g. pull BQ logs → write post-mortem).

Architecture
────────────

  ┌─ TaskAgent (LlmAgent — planner) ──────────────────────────────────────┐
  │  Decides: independent tasks → ParallelDispatcher                      │
  │           dependent tasks   → sequential transfer_to_agent            │
  │                                                                        │
  │   sub_agents:                                                          │
  │     • ParallelDispatcher (ParallelAgent)                               │
  │         ├── AnalyticsAgent                                             │
  │         ├── HRAgent                                                    │
  │         ├── ITHelpdeskAgent                                            │
  │         └── DeveloperAgent                                             │
  │     • AnalyticsAgent   (also direct, for sequential dependency)        │
  │     • HRAgent                                                          │
  │     • ITHelpdeskAgent                                                  │
  │     • DeveloperAgent                                                   │
  └────────────────────────────────────────────────────────────────────────┘

Builder function signature
──────────────────────────
  build_task_agent(settings, specialist_agents) -> LlmAgent

The orchestrator calls build_task_agent AFTER building all specialist agents
so it can inject them as sub_agents.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, ParallelAgent

from config import Settings
from memory.skill_learning import build_skill_learning_callback
from models.provider import get_model

_TASK_AGENT_INSTRUCTION = """\
You are TaskAgent, a multi-domain task planner and coordinator.

Your role is to handle requests that span more than one domain by:
1. **Decomposing** the overall request into concrete sub-tasks.
2. **Deciding** whether sub-tasks are independent or dependent.
3. **Dispatching** accordingly:
   - Independent sub-tasks (no shared data) → transfer to ParallelDispatcher
   - Dependent sub-tasks (step B needs step A's result) → sequential transfer_to_agent
4. **Aggregating** all results into a single cohesive response.

Specialist agents available
────────────────────────────
• ParallelDispatcher  — runs AnalyticsAgent + HRAgent + ITHelpdeskAgent + DeveloperAgent
                        SIMULTANEOUSLY. Use this when sub-tasks are independent.
• AnalyticsAgent      — data queries, BigQuery analysis, dashboards, reporting
• HRAgent             — HR policies, PTO, benefits, onboarding, org charts
• ITHelpdeskAgent     — IT incidents, system access, VPN, runbooks, tickets
• DeveloperAgent      — code help, debugging, repo navigation, infra, sandboxed code execution

Decision guide: parallel vs sequential
────────────────────────────────────────
Use ParallelDispatcher when:
  ✓ Sub-tasks are fully independent (e.g. HR policy + IT setup + headcount update)
  ✓ Each agent needs only the original user request, not another agent's output
  ✓ Speed matters and there is no dependency

Use sequential transfer_to_agent when:
  ✓ Agent B explicitly needs Agent A's output as input
  ✓ You need to inspect intermediate results before deciding the next step
  ✓ Only one domain is involved

Bias-for-action rules (IMPORTANT)
───────────────────────────────────
- Start executing immediately with the information you have.
- Make reasonable assumptions for missing details (use "TBD" as placeholder).
- Only pause mid-execution if you hit a genuine blocker that cannot be inferred.
- Present completed work first, THEN ask for any remaining missing details at the end.

────────────────────────────────────────────────────
Example 1 — New Employee Onboarding (PARALLEL)
────────────────────────────────────────────────────
User: "Onboard John Li, Engineering Manager, joining next Friday. No email yet."

Decision: HR checklist, IT setup, and headcount update are all INDEPENDENT.
→ transfer to ParallelDispatcher with the full context.

ParallelDispatcher runs simultaneously:
  • HRAgent:          Prepare onboarding checklist, policy docs, orientation schedule.
  • ITHelpdeskAgent:  Provision laptop, VPN, GitHub, Slack (use john.li@company.com placeholder).
  • AnalyticsAgent:   Add John Li to headcount dashboard effective next Friday.

Aggregate: Deliver unified onboarding summary. Ask only: "Please confirm John's
           company email once IT creates it to complete the account setup."

────────────────────────────────────────────────────
Example 2 — Incident Response (SEQUENTIAL — dependent)
────────────────────────────────────────────────────
User: "Checkout API 5xx errors spiking. Pull last hour of BQ logs, then write post-mortem."

Decision: Post-mortem NEEDS the BQ results first → sequential.

  Step 1 → AnalyticsAgent: "Fetch all 5xx errors from checkout API in the last 60 min."
  Step 2 → DeveloperAgent: "Given these results <paste>, write a post-mortem template."

Aggregate: Error summary + post-mortem template together.

────────────────────────────────────────────────────
Example 3 — MBR Prep (PARALLEL)
────────────────────────────────────────────────────
User: "Prepare MBR: Q3 revenue by region, headcount report, summary of open P1 incidents."

Decision: All three are independent data pulls → ParallelDispatcher.
→ transfer to ParallelDispatcher.

Aggregate: Structured MBR briefing doc.
"""


def build_task_agent(
    settings: Settings,
    specialist_agents: list,
) -> LlmAgent:
    """
    Build the hybrid TaskAgent (parallel + sequential planner).

    Args:
        settings:          Application settings.
        specialist_agents: List of specialist LlmAgent instances.

    Returns:
        An LlmAgent that routes to ParallelDispatcher or sequential agents.
    """
    # ParallelDispatcher runs all specialists simultaneously.
    # ADK ParallelAgent fans out to all sub_agents and collects their responses.
    parallel_dispatcher = ParallelAgent(
        name="ParallelDispatcher",
        description=(
            "Runs AnalyticsAgent, HRAgent, ITHelpdeskAgent, and DeveloperAgent "
            "simultaneously. Use this for independent sub-tasks that do not depend "
            "on each other's output."
        ),
        sub_agents=list(specialist_agents),
    )

    # TaskAgent sees ParallelDispatcher + individual specialists for sequential use.
    # NOTE: specialist_agents objects are shared — ParallelDispatcher holds them as
    # children; TaskAgent holds ParallelDispatcher + the same specialists directly.
    # ADK allows an agent to appear under multiple parents only if it is the SAME
    # object reference (not a copy). If ADK raises a dual-parent error here, swap
    # to sequential-only by removing specialist_agents from task_sub_agents.
    task_sub_agents = [parallel_dispatcher] + list(specialist_agents)

    return LlmAgent(
        name="TaskAgent",
        model=get_model(settings.agent_model_task_planner),
        description=(
            "Multi-step tasks requiring collaboration across Analytics, HR, "
            "IT, and Developer agents. Runs independent sub-tasks in parallel "
            "and dependent sub-tasks sequentially."
        ),
        instruction=_TASK_AGENT_INSTRUCTION,
        sub_agents=task_sub_agents,
        after_agent_callback=build_skill_learning_callback(agent_name="TaskAgent"),
    )
