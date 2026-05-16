"""
agents/orchestrator.py

Root orchestrator agent — routes incoming requests to the correct vertical
agent using LLM-driven delegation (ADK AutoFlow / transfer_to_agent).

Routing decision is made by Gemini based on each sub-agent's `description`.
No routing code needed: ADK generates transfer_to_agent() calls automatically.

Sub-agents are loaded dynamically from agents.yaml via AgentLoader.
To add a new agent, edit agents.yaml — no Python changes required.
"""
from google.adk.agents import LlmAgent

from agents.loader import build_agents_from_yaml
from config import Settings
from models.provider import get_model

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
    sub_agents = build_agents_from_yaml(settings)

    return LlmAgent(
        name="Orchestrator",
        model=get_model(settings.agent_model_orchestrator),
        description="Main entry point that routes requests to specialist agents.",
        instruction=_ORCHESTRATOR_INSTRUCTION,
        sub_agents=sub_agents,
        tools=[],
    )
