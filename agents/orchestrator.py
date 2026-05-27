"""
agents/orchestrator.py

Root orchestrator agent — routes incoming requests to the correct vertical
agent using LLM-driven delegation (ADK AutoFlow / transfer_to_agent).

Routing decision is made by Gemini based on each sub-agent's `description`.
No routing code needed: ADK generates transfer_to_agent() calls automatically.

Sub-agents are loaded dynamically from agents.yaml via AgentLoader.
To add a new agent, edit agents.yaml — no Python changes required.

TaskAgent is built separately after all specialist agents are loaded so that
the specialist agents can be injected as its sub_agents.
"""
from google.adk.agents import LlmAgent

from agents.loader import build_agents_from_yaml
from agents.task_agent import build_task_agent
from config import Settings
from models.provider import get_model

# ADK 2.0: RetryConfig — auto-retry on transient LLM failures
try:
    from google.adk.agents import RetryConfig
    _RETRY_CONFIG = RetryConfig(max_attempts=3)
except ImportError:
    _RETRY_CONFIG = None

_ORCHESTRATOR_INSTRUCTION = """
You are Hermes, an enterprise AI assistant. You receive user requests and
delegate them to the most appropriate specialist agent.

Rules:
1. Delegate the FULL user request — do not summarize or truncate it.
2. If a request spans multiple domains, split it and call each agent.
3. If the domain is unclear, ask one brief clarifying question.
4. Never answer domain questions yourself — always delegate.
"""


def build_orchestrator(settings: Settings) -> LlmAgent:
    # Build all agents from YAML — TaskAgent placeholder is in YAML but rebuilt below
    all_agents = build_agents_from_yaml(settings)

    # Specialists go under TaskAgent only — they cannot have two parents
    specialist_agents = [a for a in all_agents if a.name != "TaskAgent"]

    # Build TaskAgent with specialists injected as its sub_agents
    task_agent = build_task_agent(settings, specialist_agents)

    # Orchestrator only sees TaskAgent — specialists are TaskAgent's children
    # For single-domain requests, Orchestrator delegates to TaskAgent which
    # passes through to the right specialist.
    _orch_kwargs: dict = dict(
        name="Orchestrator",
        model=get_model(settings.agent_model_orchestrator),
        description="Main entry point that routes requests to specialist agents.",
        instruction=_ORCHESTRATOR_INSTRUCTION,
        sub_agents=[task_agent],
        tools=[],
    )
    if _RETRY_CONFIG is not None:
        _orch_kwargs["retry_config"] = _RETRY_CONFIG
    return LlmAgent(**_orch_kwargs)
