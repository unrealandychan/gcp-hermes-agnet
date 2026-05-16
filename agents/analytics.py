"""
agents/analytics.py

Analytics vertical agent — handles data queries, BigQuery analysis, and reporting.
Equipped with:
  - bigquery_tool   : execute SQL queries
  - search_tool     : search knowledge corpus (docs, schemas)
  - PreloadMemoryTool : inject long-term user memory at turn start
  - skill_retriever_tool : inject self-learned procedures at turn start
After each turn, skill_learning_callback extracts and persists a new skill.
"""
from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from config import Settings
from memory.skill_learning import build_skill_learning_callback
from models.provider import get_model
from tools.bigquery_tool import make_bigquery_tool
from tools.search_tool import make_search_tool

_INSTRUCTION = """
You are the Analytics Agent. You specialise in data analysis, SQL queries on
BigQuery, generating reports, and interpreting business metrics.

## Reasoning approach — ReAct Loop

Before every response, run this internal loop silently:

  Thought:  What is the user really asking? What data do I need?
            Do I have a matching learned skill? What assumptions am I making?
  Action:   Choose a tool (bigquery_tool / search_tool) or reason further.
  Observation: What did the tool return? Does it answer the question?
  ... (repeat Thought → Action → Observation until confident)
  Answer:   Deliver the final structured response.

Rules:
- Work through the full loop before replying — never answer from the first guess.
- Use learned skills (injected at turn start) before writing new SQL.
- Validate SQL mentally (correct table names, date ranges, aggregations) before executing.
- If data is missing, state your assumption and proceed — do NOT ask first.
- Only pause for user input if a genuine blocker cannot be inferred (e.g. unknown table).
- Return results with: query used, key findings, interpretation, assumptions made.
"""


def build_analytics_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="AnalyticsAgent",
        model=get_model(settings.agent_model_analytics),
        description=(
            "Handles data analysis, BigQuery SQL queries, dashboards, and reporting. "
            "Use for questions about metrics, sales data, usage trends, or any structured data."
        ),
        instruction=_INSTRUCTION,
        tools=[
            make_bigquery_tool(settings),
            make_search_tool(settings),
            PreloadMemoryTool(),
        ],
        after_agent_callback=build_skill_learning_callback(agent_name="AnalyticsAgent"),
    )
