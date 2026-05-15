"""
agents/developer.py

Developer assistant agent — helps engineers with code, debugging, and infrastructure.
"""
import logging

from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from config import Settings
from memory.skill_learning import build_skill_learning_callback
from models.provider import get_model
from tools.drive_tool import list_drive_folder_tool, read_drive_tool, search_drive_tool
from tools.search_tool import make_search_tool
from tools.storage_tool import make_storage_tool

logger = logging.getLogger(__name__)

# ── Code execution (Agent Sandbox) ────────────────────────────────────────────
# BuiltInCodeExecutionTool runs code in Vertex AI's managed secure sandbox.
# Gracefully skipped if the ADK version does not yet export the tool.
try:
    from google.adk.tools.built_in_code_execution_tool import BuiltInCodeExecutionTool
    _code_execution_tool: BuiltInCodeExecutionTool | None = BuiltInCodeExecutionTool()
except ImportError:
    logger.info(
        "BuiltInCodeExecutionTool not available in this ADK version — "
        "code execution disabled for DeveloperAgent."
    )
    _code_execution_tool = None

_INSTRUCTION = """
You are the Developer Agent. You assist engineers with code reviews, debugging,
infrastructure questions, and navigating internal repositories and documentation.

When answering:
1. Check injected skills for a matching learned procedure or pattern.
2. Use search_tool to look up internal API docs, architecture docs, or code references.
3. Use storage_tool to read configuration files or deployment manifests when needed.
4. Use search_drive_files / read_drive_file to access architecture diagrams, design
   docs, ADRs, or specs stored in Google Drive.
5. Use google_search to look up public library docs, Stack Overflow answers, GitHub
   issues, or vendor release notes.
6. Use the code execution tool to run and verify code snippets, data transforms,
   or shell commands in a secure sandbox before recommending them.
7. Provide runnable, production-quality code examples.
8. For security-sensitive operations (IAM, secrets, network rules), explicitly note
   the security implications and recommended best practices.
"""


def build_developer_agent(settings: Settings) -> LlmAgent:
    tools = [
        make_search_tool(settings),
        make_storage_tool(settings),
        PreloadMemoryTool(),
        google_search,
        # Drive — read architecture docs, design specs, ADRs
        search_drive_tool,
        read_drive_tool,
        list_drive_folder_tool,
    ]
    if _code_execution_tool is not None:
        tools.append(_code_execution_tool)

    return LlmAgent(
        name="DeveloperAgent",
        model=get_model(settings.agent_model_developer),
        description=(
            "Assists engineers with code, debugging, architecture questions, "
            "CI/CD pipelines, infrastructure, and internal developer documentation. "
            "Can execute code in a secure sandbox to verify solutions."
        ),
        instruction=_INSTRUCTION,
        tools=tools,
        after_agent_callback=build_skill_learning_callback(agent_name="DeveloperAgent"),
    )
