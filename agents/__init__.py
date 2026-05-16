"""
agents/__init__.py
Exports the root orchestrator agent and AdkApp wrapper used for deployment.
"""
from agents.orchestrator import build_orchestrator
from vertexai import agent_engines

from config import get_settings


def build_agent():
    """Return the raw ADK Agent — used by the local gateway Runner."""
    settings = get_settings()
    return build_orchestrator(settings)


def build_adk_app() -> agent_engines.AdkApp:
    """Return an AdkApp wrapping the full agent graph — used for Agent Runtime deploy only."""
    return agent_engines.AdkApp(agent=build_agent(), enable_tracing=True)
