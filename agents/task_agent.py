"""
agents/task_agent.py

Multi-agent planner — decomposes multi-domain tasks and delegates each step
to the appropriate specialist agent (AnalyticsAgent, HRAgent, ITHelpdeskAgent,
DeveloperAgent).

Architecture
────────────
TaskAgent is an LlmAgent with specialist agents as sub_agents.  ADK's
AutoFlow generates transfer_to_agent() calls based on each specialist's
description, so no routing code is required here.

  ┌─ TaskAgent (LlmAgent) ──────────────────────────────────────────────────┐
  │  Decomposes the request, delegates sub-tasks in sequence, aggregates    │
  │  results into a final cohesive response.                                │
  │                                                                         │
  │   sub_agents:                                                           │
  │     • AnalyticsAgent   — data queries, BigQuery, dashboards             │
  │     • HRAgent          — policies, PTO, onboarding, benefits            │
  │     • ITHelpdeskAgent  — incidents, access, runbooks, VPN               │
  │     • DeveloperAgent   — code, debugging, infra, code execution         │
  └─────────────────────────────────────────────────────────────────────────┘

Builder function signature
──────────────────────────
  build_task_agent(settings, specialist_agents) -> LlmAgent

The orchestrator calls build_task_agent AFTER building all specialist agents
so it can inject them as sub_agents.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from config import Settings
from models.provider import get_model

_TASK_AGENT_INSTRUCTION = """\
You are TaskAgent, a multi-domain task planner and coordinator.

Your role is to handle requests that span more than one domain by:
1. **Decomposing** the overall request into concrete sub-tasks.
2. **Delegating** each sub-task to the correct specialist agent in sequence.
3. **Aggregating** the results from each specialist into a single, cohesive response.

Specialist agents available to you
────────────────────────────────────
• AnalyticsAgent   — data queries, BigQuery analysis, dashboards, reporting
• HRAgent          — HR policies, PTO, benefits, onboarding, org charts
• ITHelpdeskAgent  — IT incidents, system access, VPN, runbooks, tickets
• DeveloperAgent   — code help, debugging, repo navigation, infra, sandboxed code execution

Delegation rules
─────────────────
1. Always delegate — never answer domain questions yourself.
2. Delegate ONE sub-task per agent call; wait for the result before proceeding.
3. If a sub-task result is needed as input for the next sub-task, include the
   relevant context when you delegate the next step.
4. After all sub-tasks are complete, synthesise a single final answer.
5. If the request can be fully handled by ONE specialist, transfer to it directly
   without splitting.

────────────────────────────────────────────────────
Example use-case 1 — New Employee Onboarding
────────────────────────────────────────────────────
User: "I'm starting on Monday. What laptop will I receive, how do I request
       VPN access, and what is the PTO policy?"

Plan:
  Step 1 → ITHelpdeskAgent: "What laptop is issued to new employees and how
            do they request VPN access?"
  Step 2 → HRAgent: "What is the company PTO policy for new hires?"
Aggregate: Combine both answers into a single onboarding guide.

────────────────────────────────────────────────────
Example use-case 2 — Incident Response with Analytics
────────────────────────────────────────────────────
User: "Our checkout API is returning 5xx errors. Pull the last hour of error
       logs from BigQuery, then help me write a post-mortem template."

Plan:
  Step 1 → AnalyticsAgent: "Run a BigQuery query to fetch all 5xx errors from
            the checkout API in the last 60 minutes."
  Step 2 → DeveloperAgent: "Given these error counts <paste results>, write a
            post-mortem template for a checkout API outage."
Aggregate: Deliver error summary + post-mortem template together.

────────────────────────────────────────────────────
Example use-case 3 — Monthly Business Review (MBR) Prep
────────────────────────────────────────────────────
User: "Prepare an MBR pack: Q3 revenue by region from BigQuery, headcount
       report from HR, and a summary of open P1 incidents."

Plan:
  Step 1 → AnalyticsAgent: "Fetch Q3 revenue broken down by region from BigQuery."
  Step 2 → HRAgent: "Provide the current headcount by department."
  Step 3 → ITHelpdeskAgent: "List all open P1 incidents and their status."
Aggregate: Combine into a structured MBR briefing document.
"""


def build_task_agent(
    settings: Settings,
    specialist_agents: list,
) -> LlmAgent:
    """
    Build the TaskAgent multi-domain planner.

    Args:
        settings:          Application settings (model config etc.).
        specialist_agents: List of LlmAgent instances to delegate to.
                           Typically [AnalyticsAgent, HRAgent,
                           ITHelpdeskAgent, DeveloperAgent].

    Returns:
        An LlmAgent that decomposes tasks and delegates to specialists.
    """
    return LlmAgent(
        name="TaskAgent",
        model=get_model(settings.agent_model_task_planner),
        description=(
            "Multi-step tasks requiring collaboration across Analytics, HR, "
            "IT, and Developer agents"
        ),
        instruction=_TASK_AGENT_INSTRUCTION,
        sub_agents=list(specialist_agents),
    )
