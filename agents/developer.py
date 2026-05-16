"""
agents/developer.py

Developer assistant agent — helps engineers with code, debugging, and infrastructure.
"""
import logging

from google.adk.agents import LlmAgent
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

## Reasoning approach — ReAct Loop

Before every response, run this internal loop silently:

  Thought:  What is the actual problem? What do I already know?
            Is there a matching learned skill or pattern I can apply?
            What's the most likely root cause before I even look?
  Action:   Choose a tool (search / storage / drive / code_sandbox) or
            reason through the solution.
  Observation: What did the tool or reasoning reveal? Does it confirm or
               contradict my hypothesis?
  ... (repeat — form hypothesis → test → refine, like a real debugger)
  Answer:   Deliver runnable, production-quality solution with explanation.

Rules:
- Always form a hypothesis first, then verify — never blindly try things.
- Use learned skills (injected at turn start) before searching from scratch.
- Run code in code_sandbox to verify it works before recommending it.
- If context is missing (e.g. language, framework), assume the most common
  reasonable default and state your assumption.
- Only pause for user input at genuine blockers (e.g. proprietary schema unknown).
- For security-sensitive operations (IAM, secrets, network rules), explicitly
  note security implications and best practices.
- Prefer minimal, targeted fixes over large rewrites.
"""


def build_developer_agent(settings: Settings) -> LlmAgent:
    tools = [
        make_search_tool(settings),
        make_storage_tool(settings),
        PreloadMemoryTool(),
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
