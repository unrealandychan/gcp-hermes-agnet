"""
tools/mcp_connector.py

Model Context Protocol (MCP) toolset factory.
https://modelcontextprotocol.io/

Connects ADK agents to any MCP-compatible tool server — local (stdio) or
remote (SSE). Each MCPToolset exposes all tools provided by the server as
native ADK FunctionTools, so no agent-side changes are needed when new MCP
tools are added to the server.

Common MCP servers:
  Filesystem  — npx @modelcontextprotocol/server-filesystem /path
  GitHub      — npx @modelcontextprotocol/server-github
  PostgreSQL  — npx @modelcontextprotocol/server-postgres <conn-url>
  Slack       — npx @modelcontextprotocol/server-slack
  Custom      — any server implementing the MCP spec

Configuration (.env):
  MCP_FILESYSTEM_PATH=/data/shared      # enable local filesystem MCP server
  MCP_SSE_SERVER_URL=http://host/mcp/sse  # enable a remote SSE MCP server
  MCP_SSE_AUTH_TOKEN=<token>            # optional Bearer token for SSE server
"""
from __future__ import annotations

import logging
from typing import Any

from config import Settings

logger = logging.getLogger(__name__)


def make_filesystem_mcp_toolset(path: str) -> Any | None:
    """
    Return an ADK MCPToolset backed by the official MCP filesystem server.

    The server is launched as a subprocess via npx on first use.
    Requires Node.js / npx installed on the host.

    Args:
        path: Absolute directory the agent is allowed to read/write.

    Returns:
        MCPToolset instance or None if ADK MCP support is unavailable.
    """
    try:
        from google.adk.tools.mcp_tool import MCPToolset, StdioServerParameters  # noqa: PLC0415

        return MCPToolset(
            connection_params=StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", path],
            )
        )
    except ImportError:
        logger.warning(
            "google.adk.tools.mcp_tool not available — "
            "MCP filesystem toolset disabled. Upgrade google-adk."
        )
        return None


def make_sse_mcp_toolset(
    server_url: str,
    auth_token: str | None = None,
) -> Any | None:
    """
    Return an ADK MCPToolset connected to a remote SSE MCP server.

    Args:
        server_url:  Full URL of the MCP SSE endpoint.
        auth_token:  Optional Bearer token sent in every request header.

    Returns:
        MCPToolset instance or None if ADK MCP support is unavailable.
    """
    try:
        from google.adk.tools.mcp_tool import MCPToolset, SseServerParams  # noqa: PLC0415

        headers: dict[str, str] = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        return MCPToolset(
            connection_params=SseServerParams(url=server_url, headers=headers)
        )
    except ImportError:
        logger.warning(
            "google.adk.tools.mcp_tool not available — "
            "MCP SSE toolset disabled. Upgrade google-adk."
        )
        return None


def get_configured_mcp_tools(settings: Settings) -> list[Any]:
    """
    Build and return all MCP toolsets that are configured in settings.

    Each toolset is a single object that ADK expands into individual
    FunctionTools at agent-build time, so pass the list directly to
    LlmAgent(tools=[...]).

    Returns an empty list when no MCP servers are configured.
    """
    tools: list[Any] = []

    fs_path = getattr(settings, "mcp_filesystem_path", "")
    if fs_path:
        toolset = make_filesystem_mcp_toolset(fs_path)
        if toolset is not None:
            tools.append(toolset)
            logger.info("MCP filesystem toolset enabled: %s", fs_path)

    sse_url = getattr(settings, "mcp_sse_server_url", "")
    if sse_url:
        token = getattr(settings, "mcp_sse_auth_token", "") or None
        toolset = make_sse_mcp_toolset(sse_url, auth_token=token)
        if toolset is not None:
            tools.append(toolset)
            logger.info("MCP SSE toolset enabled: %s", sse_url)

    return tools
