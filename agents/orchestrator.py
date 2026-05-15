"""
agents/orchestrator.py

Root orchestrator agent — routes incoming requests to the correct vertical
agent using LLM-driven delegation (ADK AutoFlow / transfer_to_agent).

Routing decision is made by Gemini based on each sub-agent's `description`.
No routing code needed: ADK generates transfer_to_agent() calls automatically.
"""
from google.adk.agents import LlmAgent
from google.adk.tools import google_search

from agents.analytics import build_analytics_agent
from agents.developer import build_developer_agent
from agents.hr import build_hr_agent
from agents.it_helpdesk import build_it_helpdesk_agent
from config import Settings
from models.provider import get_model

_ORCHESTRATOR_INSTRUCTION = """
You are Hermes, an enterprise AI assistant. You receive user requests and
delegate them to the most appropriate specialist agent.

Specialist agents available:
- AnalyticsAgent: data queries, BigQuery analysis, dashboards, reporting
- ITHelpdeskAgent: IT issues, system access, incident tickets, runbooks
- HRAgent: HR policies, PTO, benefits, onboarding, org questions
- DeveloperAgent: code help, debugging, repo navigation, infra questions

Rules:
1. Delegate the FULL user request — do not summarize or truncate it.
2. If a request spans multiple domains, split it and call each agent.
3. If the domain is unclear, ask one brief clarifying question.
4. Never answer domain questions yourself — always delegate.
5. Use google_search only for general real-world context before routing
   (e.g. checking if a CVE is public, looking up an error message).
"""


def build_orchestrator(settings: Settings) -> LlmAgent:
    analytics = build_analytics_agent(settings)
    it_helpdesk = build_it_helpdesk_agent(settings)
    hr = build_hr_agent(settings)
    developer = build_developer_agent(settings)

    return LlmAgent(
        name="Orchestrator",
        model=get_model(settings.agent_model_orchestrator),
        description="Main entry point that routes requests to specialist agents.",
        instruction=_ORCHESTRATOR_INSTRUCTION,
        sub_agents=[analytics, it_helpdesk, hr, developer],
        tools=[google_search],
    )
