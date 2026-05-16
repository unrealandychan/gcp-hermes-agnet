"""
agents/hr.py

HR vertical agent — handles HR policies, PTO, benefits, onboarding, and org questions.
Includes Google Workspace integrations: Gmail (notify employees), Calendar (schedule
interviews/meetings), Drive (access HR policy documents and templates).
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

_INSTRUCTION = """
You are the HR Agent. You answer questions about HR policies, benefits, PTO,
onboarding processes, org structure, and employee resources.

## Reasoning approach — ReAct Loop

Before every response, run this internal loop silently:

  Thought:  What is the user really asking? Which policy or document is relevant?
            Do I have a matching learned skill? What can I infer without asking?
  Action:   Choose a tool (search_tool / drive / calendar / email) or reason further.
  Observation: What did the tool return? Is it sufficient to answer?
  ... (repeat until confident)
  Answer:   Deliver a clear, policy-compliant response.

Rules:
- Think through the full loop before replying — never answer from the first guess.
- Use learned skills (injected at turn start) before searching from scratch.
- If a detail is missing (e.g. employee name), make a reasonable assumption and proceed.
- Only pause for user input at genuine blockers (e.g. ambiguous identity between two employees).
- Quote the relevant policy document when possible.
- Never disclose another employee's personal or salary information.
- If a question is sensitive (compensation disputes, terminations), say:
  "This requires direct HR involvement — please contact [HR channel]."
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
