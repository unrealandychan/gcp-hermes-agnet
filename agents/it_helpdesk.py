"""
agents/it_helpdesk.py

IT Helpdesk vertical agent — handles incidents, access requests, runbooks, and IT FAQs.
Includes Google Workspace integrations: Gmail (incident notifications), Calendar
(maintenance windows), Drive (runbooks and IT documentation).
"""
from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from config import Settings
from memory.skill_learning import build_skill_learning_callback
from models.provider import get_model
from tools.calendar_tool import check_availability_tool, create_event_tool, list_events_tool
from tools.drive_tool import list_drive_folder_tool, read_drive_tool, search_drive_tool
from tools.gmail_tool import get_email_tool, search_emails_tool, send_email_tool
from tools.search_tool import make_search_tool
from tools.storage_tool import make_storage_tool

_INSTRUCTION = """
You are the IT Helpdesk Agent. You resolve IT incidents, guide users through
runbooks, handle access requests, and answer IT policy questions.

## Reasoning approach — ReAct Loop

Before every response, run this internal loop silently:

  Thought:  What is the issue? Have I seen this before (learned skill)?
            What information do I already have vs what do I need?
  Action:   Choose a tool (search_tool / storage / drive / email / calendar)
            or reason through the resolution steps.
  Observation: What did the tool return? Does it resolve the issue?
  ... (repeat until a clear resolution path is found)
  Answer:   Deliver step-by-step resolution with escalation path if needed.

Rules:
- Think through the full loop before replying — never suggest the first fix that comes to mind.
- Check learned skills (injected at turn start) for existing runbooks before searching.
- Assume reasonable defaults (e.g. standard OS, standard network config) when details missing.
- Only pause for user input at genuine blockers (e.g. unknown asset tag, ambiguous user).
- Provide numbered, actionable steps.
- Escalate clearly when human intervention is needed: "ESCALATE: <reason> → contact <team>".
"""


def build_it_helpdesk_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="ITHelpdeskAgent",
        model=get_model(settings.agent_model_it_helpdesk),
        description=(
            "Handles IT issues: system access, password resets, incidents, runbooks, "
            "network/VPN problems, IT policy questions, and Google Workspace actions "
            "(incident emails, maintenance calendar events, Drive runbooks)."
        ),
        instruction=_INSTRUCTION,
        tools=[
            make_search_tool(settings),
            make_storage_tool(settings),
            PreloadMemoryTool(),
            # Gmail
            send_email_tool,
            search_emails_tool,
            get_email_tool,
            # Calendar
            create_event_tool,
            list_events_tool,
            check_availability_tool,
            # Drive
            search_drive_tool,
            read_drive_tool,
            list_drive_folder_tool,
        ],
        after_agent_callback=build_skill_learning_callback(agent_name="ITHelpdeskAgent"),
    )
