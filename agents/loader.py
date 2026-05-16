"""
agents/loader.py

AgentLoader — reads agents.yaml and builds sub-agents dynamically.

The loader supports two modes per agent entry:
1. **Custom builder** — if a builder function is registered in _CUSTOM_BUILDERS
   for that agent name, it is called with (settings) and its return value is used.
2. **Generic builder** — if no custom builder is registered, a generic LlmAgent
   is constructed from the YAML config using _TOOL_FACTORIES to resolve tool names.

This means adding a new agent requires only editing agents.yaml, with no Python
changes, unless the agent needs custom tool logic.

Environment variable substitution: values like ${VAR:-default} in agents.yaml
are resolved against os.environ before parsing.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Callable

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("PyYAML is required. Run: pip install pyyaml") from exc

from google.adk.agents import LlmAgent
from google.adk.tools import google_search

from config import Settings
from models.provider import get_model

logger = logging.getLogger(__name__)

_AGENTS_YAML = Path(__file__).parent.parent / "agents.yaml"
_ENV_VAR_RE = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


# ── Tool factory registry ─────────────────────────────────────────────────────
# Maps the tool name used in agents.yaml → a callable(settings) -> tool object.
# Import lazily inside lambdas to keep conftest stub registration effective.

def _tool_factories(settings: Settings) -> dict:
    import tools.bigquery_tool as _bq
    import tools.search_tool as _st
    import tools.storage_tool as _stor

    factories: dict[str, object] = {
        "search": _st.make_search_tool(settings),
        "bigquery": _bq.make_bigquery_tool(settings),
        "storage": _stor.make_storage_tool(settings),
        "google_search": google_search,
    }

    # Optional tools — only added when configured
    if settings.knowledge_corpus_name:
        try:
            from google.adk.tools.preload_memory_tool import PreloadMemoryTool
            factories["rag_knowledge"] = PreloadMemoryTool()
        except Exception:  # noqa: BLE001
            logger.warning("Could not load rag_knowledge tool; knowledge_corpus_name may be invalid.")

    if settings.mcp_filesystem_path:
        try:
            from google.adk.tools.mcp_tool import MCPToolset, StdioServerParameters
            factories["mcp_filesystem"] = MCPToolset(
                connection_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", settings.mcp_filesystem_path],
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not load mcp_filesystem tool.")

    if settings.mcp_sse_server_url:
        try:
            from google.adk.tools.mcp_tool import MCPToolset, SseServerParams
            factories["mcp_sse"] = MCPToolset(
                connection_params=SseServerParams(
                    url=settings.mcp_sse_server_url,
                    headers={"Authorization": f"Bearer {settings.mcp_sse_auth_token}"}
                    if settings.mcp_sse_auth_token
                    else {},
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not load mcp_sse tool.")

    if settings.model_armor_template_id:
        try:
            from google.adk.tools.built_in_code_execution_tool import BuiltInCodeExecutionTool
            factories["code_sandbox"] = BuiltInCodeExecutionTool()
        except Exception:  # noqa: BLE001
            logger.warning("Could not load code_sandbox tool.")

    return factories


# ── Custom builder registry ───────────────────────────────────────────────────
# Maps agent name → builder callable(settings) -> LlmAgent.
# Register here when an agent needs logic beyond "pick tools from YAML".

def _custom_builders() -> dict[str, Callable[[Settings], LlmAgent]]:
    from agents.analytics import build_analytics_agent
    from agents.developer import build_developer_agent
    from agents.hr import build_hr_agent
    from agents.it_helpdesk import build_it_helpdesk_agent

    return {
        "AnalyticsAgent": build_analytics_agent,
        "ITHelpdeskAgent": build_it_helpdesk_agent,
        "HRAgent": build_hr_agent,
        "DeveloperAgent": build_developer_agent,
        # TaskAgent is intentionally omitted here.  It is built by
        # agents/orchestrator.py AFTER all specialist agents are available
        # so that the specialists can be injected as its sub_agents.
    }


# ── YAML loading ──────────────────────────────────────────────────────────────

def _resolve_env_vars(text: str) -> str:
    """Substitute ${VAR:-default} patterns using os.environ."""
    def _replace(m: re.Match) -> str:
        var, default = m.group(1), m.group(2) or ""
        return os.environ.get(var, default)
    return _ENV_VAR_RE.sub(_replace, text)


def load_agents_yaml(path: str | Path | None = None) -> list[dict]:
    """Parse agents.yaml and return the list of agent config dicts."""
    yaml_path = Path(path) if path else _AGENTS_YAML
    raw = yaml_path.read_text(encoding="utf-8")
    resolved = _resolve_env_vars(raw)
    data = yaml.safe_load(resolved) or {}
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        raise ValueError(f"agents.yaml must have a top-level 'agents' list, got: {type(agents)}")
    return agents


# ── Agent building ─────────────────────────────────────────────────────────────

def build_agents_from_yaml(
    settings: Settings,
    yaml_path: str | Path | None = None,
) -> list[LlmAgent]:
    """
    Load agents.yaml and build all configured sub-agents.

    Returns a list of LlmAgent instances in the order they appear in the YAML.
    """
    configs = load_agents_yaml(yaml_path)
    tool_map = _tool_factories(settings)
    builder_map = _custom_builders()

    agents: list[LlmAgent] = []
    for cfg in configs:
        name = cfg.get("name", "")
        if not name:
            logger.warning("Skipping agent entry with no 'name' field: %s", cfg)
            continue

        try:
            if name in builder_map:
                agent = builder_map[name](settings)
            else:
                agent = _build_generic(cfg, settings, tool_map)
            agents.append(agent)
            logger.debug("Built agent: %s", name)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to build agent '%s' — skipping.", name)

    logger.info("AgentLoader: built %d agent(s) from agents.yaml", len(agents))
    return agents


def _build_generic(cfg: dict, settings: Settings, tool_map: dict) -> LlmAgent:
    """Build a generic LlmAgent from a YAML config dict."""
    name = cfg["name"]
    description = cfg.get("description", name)
    model_name = cfg.get("model", settings.agent_model_orchestrator)
    tool_keys: list[str] = cfg.get("tools", [])

    tools = []
    for key in tool_keys:
        if key in tool_map:
            tools.append(tool_map[key])
        else:
            logger.warning(
                "Agent '%s': unknown tool '%s' — skipping. Valid keys: %s",
                name, key, sorted(tool_map.keys()),
            )

    # ── Gemini API constraint: google_search (grounding) cannot be mixed with
    # other function tools. If google_search is present alongside other tools,
    # drop it and log a warning rather than letting the agent crash at runtime.
    from google.adk.tools import google_search as _gs  # noqa: PLC0415
    if _gs in tools and len(tools) > 1:
        logger.warning(
            "Agent '%s': google_search cannot be combined with other tools "
            "(Gemini API constraint). Removing google_search — use the "
            "Orchestrator for web search.",
            name,
        )
        tools = [t for t in tools if t is not _gs]

    return LlmAgent(
        name=name,
        model=get_model(model_name),
        description=description,
        tools=tools if tools else [],
    )
