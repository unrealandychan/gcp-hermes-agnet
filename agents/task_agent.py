"""
agents/task_agent.py

Long-running, autonomous ReAct-loop agent built on ADK's LoopAgent.

Architecture
────────────
LoopAgent orchestrates two child agents in a fixed sequence each iteration:

  ┌─ LoopAgent (max_iterations=50) ──────────────────────────────────────┐
  │   1. PlannerAgent  — refines the plan and picks the next action       │
  │   2. ExecutorAgent — calls tools to execute one action; may signal    │
  │                      completion by calling finish_task(summary)        │
  └──────────────────────────────────────────────────────────────────────┘

The ADK LoopAgent repeats the sequence until any sub-agent's response
contains `escalate=True` (triggered by finish_task).  It also exits on
`max_iterations` so runaway loops are impossible.

Why LoopAgent instead of plain LlmAgent?
  • Plain LlmAgent uses Gemini's native function-calling loop, which is
    great for short multi-tool tasks but times out within a single request.
  • LoopAgent checkpoints state between iterations via the session service,
    meaning each "turn" is a short LLM call.  The overall task can span
    hundreds of turns and run for up to 1 hour without hitting any single
    LLM call timeout.

Max runtime:
  50 iterations × ~60 s worst-case per iteration ≈ 50 min (well under 1 h).
  Increase MAX_ITERATIONS to extend.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import FunctionTool

from config import Settings
from models.provider import get_model
from tools.bigquery_tool import run_bigquery_query
from tools.search_tool import search_knowledge_base
from tools.scheduler_tool import (
    delete_scheduled_task,
    list_scheduled_tasks,
    schedule_agent_task,
)
from tools.storage_tool import read_gcs_file, write_gcs_file

MAX_ITERATIONS = 50

# ── finish_task tool ───────────────────────────────────────────────────────────
# ExecutorAgent calls this to signal that the overall task is complete.
# Returning escalate=True causes the LoopAgent to exit.


async def finish_task(summary: str) -> dict:  # noqa: D401
    """
    Signal that the long-running task is fully complete.

    Call this when you have produced the final result and there is nothing
    more to do.  Pass a concise summary of the outcome as `summary`.

    Args:
        summary: Human-readable summary of what was accomplished.

    Returns:
        A completion marker dict (do not parse; just return it to the user).
    """
    return {"status": "complete", "summary": summary, "escalate": True}


_finish_tool = FunctionTool(func=finish_task)


# ── PlannerAgent ───────────────────────────────────────────────────────────────

_PLANNER_INSTRUCTION = """
You are the Planner for a long-running autonomous task.

Your only job in each iteration is to review what has been done so far
(from the session history) and write an updated, numbered action plan.

Rules:
1. Output ONLY the updated plan — numbered list of remaining steps.
2. Do NOT call any tools.
3. Keep each step concrete and actionable.
4. If the task is already complete (ExecutorAgent finished), output: DONE.
"""


def _build_planner(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="PlannerAgent",
        model=get_model(settings.agent_model_task_planner),
        description="Maintains and updates the action plan each iteration.",
        instruction=_PLANNER_INSTRUCTION,
    )


# ── ExecutorAgent ──────────────────────────────────────────────────────────────

_EXECUTOR_INSTRUCTION = """
You are the Executor for a long-running autonomous task.

In each iteration you:
1. Read the current plan from the Planner.
2. Execute EXACTLY ONE step from the plan using the available tools.
3. Report the outcome clearly (what you did, what you found).
4. If ALL steps are complete, call finish_task(summary=<concise summary>).

Available tools:
  - run_bigquery_query      — execute a BigQuery SQL query
  - search_knowledge_base   — search the enterprise knowledge base (RAG)
  - read_gcs_file           — read a file from GCS
  - write_gcs_file          — write a file to GCS (for storing interim results)
  - schedule_agent_task     — schedule THIS agent to run a follow-up task at a
                               future time or on a recurring cron schedule.
                               Use this when the task requires future action,
                               e.g. "send a report every Monday" or "check
                               again tomorrow".
  - delete_scheduled_task   — cancel a previously created scheduled task
  - list_scheduled_tasks    — list all scheduled tasks for this project
  - finish_task             — ONLY call when the entire task is done

Self-scheduling guidance:
  When a task needs to recur or be followed up later, call schedule_agent_task
  BEFORE calling finish_task so the future run is registered.
  Example: task="Send weekly sales summary", schedule="0 9 * * 1" (Mondays 9AM),
           job_name="weekly-sales-summary"

Rules:
  - Execute ONE step per iteration — do not try to rush through all steps.
  - Store large intermediate results in GCS (tmp/<task_id>/<step>.txt) rather
    than in the conversation, to avoid context overflow.
  - Be explicit about failures; the Planner will adapt the plan accordingly.
"""


def _build_executor(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="ExecutorAgent",
        model=get_model(settings.agent_model_task_executor),
        description="Executes one action step per iteration using tools.",
        instruction=_EXECUTOR_INSTRUCTION,
        tools=[
            FunctionTool(func=run_bigquery_query),
            FunctionTool(func=search_knowledge_base),
            FunctionTool(func=read_gcs_file),
            FunctionTool(func=write_gcs_file),
            FunctionTool(func=schedule_agent_task),
            FunctionTool(func=delete_scheduled_task),
            FunctionTool(func=list_scheduled_tasks),
            _finish_tool,
        ],
    )


# ── Public builder ─────────────────────────────────────────────────────────────


def build_task_agent(settings: Settings) -> LoopAgent:
    """
    Build the long-running task LoopAgent.

    Returns:
        A LoopAgent that autonomously executes multi-step tasks, iterating
        up to MAX_ITERATIONS times before stopping.
    """
    return LoopAgent(
        name="TaskAgent",
        description=(
            "Autonomously executes long-running, multi-step tasks using a "
            "plan-execute-observe loop.  Suitable for tasks that require many "
            "tool calls and could take up to 1 hour to complete."
        ),
        sub_agents=[
            _build_planner(settings),
            _build_executor(settings),
        ],
        max_iterations=MAX_ITERATIONS,
    )
