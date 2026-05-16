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

When answering:
1. Check your injected skills — use a matching learned procedure if one exists.
2. Use bigquery_tool to run queries. Always validate SQL before executing.
3. Use search_tool to look up dataset schemas or documentation.
4. Return results in a clear, structured format with a brief interpretation.
5. State any assumptions you made about the data.
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
