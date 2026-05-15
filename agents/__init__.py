"""
agents/__init__.py
Exports the root orchestrator agent and AdkApp wrapper used for deployment.
"""
from agents.orchestrator import build_orchestrator
from vertexai import agent_engines

from config import get_settings


def build_adk_app() -> agent_engines.AdkApp:
    """Return an AdkApp wrapping the full agent graph — used for Agent Runtime deploy."""
    settings = get_settings()
    orchestrator = build_orchestrator(settings)
    return agent_engines.AdkApp(agent=orchestrator, enable_tracing=True)
