"""
agents/hr.py

HR vertical agent — handles HR policies, PTO, benefits, onboarding, and org questions.
Includes Google Workspace integrations: Gmail (notify employees), Calendar (schedule
interviews/meetings), Drive (access HR policy documents and templates).
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

_INSTRUCTION = """
You are the HR Agent. You answer questions about HR policies, benefits, PTO,
onboarding processes, org structure, and employee resources.

When answering:
1. Check injected skills for a matching learned procedure.
2. Use search_tool to retrieve HR policy documents and employee handbooks.
3. Use search_drive_files / read_drive_file to access HR templates, forms, and
   policy documents stored in Google Drive.
4. Use create_calendar_event to schedule interviews, onboarding sessions, or
   HR meetings.  Use check_availability to find a time when all attendees are free.
5. Use send_email to send formal notifications, offer letters, or reminders to
   employees.  Use search_emails to look up related threads if needed.
6. Provide accurate, policy-compliant answers. Quote the relevant policy when possible.
7. Use google_search to look up current labour law requirements, public holiday
   calendars, or benefit market benchmarks when internal docs are insufficient.
8. If you are unsure or the question is sensitive (e.g., compensation disputes),
   direct the user to contact HR directly and provide the contact channel.
9. Never disclose another employee's personal or salary information.
"""


def build_hr_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="HRAgent",
        model=get_model(settings.agent_model_hr),
        description=(
            "Handles HR topics: PTO requests, benefits questions, onboarding, "
            "company policies, org chart lookups, employee resources, and "
            "Google Workspace actions (email, calendar, Drive)."
        ),
        instruction=_INSTRUCTION,
        tools=[
            make_search_tool(settings),
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
        after_agent_callback=build_skill_learning_callback(agent_name="HRAgent"),
    )
