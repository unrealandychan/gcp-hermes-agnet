"""
agents/it_helpdesk.py

IT Helpdesk vertical agent — handles incidents, access requests, runbooks, and IT FAQs.
Includes Google Workspace integrations: Gmail (incident notifications), Calendar
(maintenance windows), Drive (runbooks and IT documentation).
"""
from google.adk.agents import LlmAgent
from google.adk.tools import google_search
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

When answering:
1. Check injected skills for a matching learned procedure.
2. Use search_tool to retrieve runbooks and IT knowledge base articles.
3. Use storage_tool to read or write incident files in the IT storage bucket.
4. Use search_drive_files / read_drive_file to access IT runbooks, SOPs, and
   architecture diagrams stored in Google Drive.
5. Use create_calendar_event to schedule maintenance windows or incident
   retrospectives.  Use check_availability to find a slot for all stakeholders.
6. Use send_email to send incident notifications, status updates, or post-mortem
   summaries to affected users or the on-call team.
7. Use google_search to look up public CVEs, vendor advisories, or error messages
   not covered by internal runbooks.
8. Provide step-by-step resolution guidance.
9. Escalate clearly if the issue requires human intervention (say "ESCALATE: <reason>").
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
            google_search,
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
