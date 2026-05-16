"""
tests/tools/test_mcp_connector.py

Unit tests for tools/mcp_connector.py.

The ADK MCP imports are always mocked so tests run without google-adk
or Node.js installed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


from tools.mcp_connector import (
    get_configured_mcp_tools,
    make_filesystem_mcp_toolset,
    make_sse_mcp_toolset,
)


# ── make_filesystem_mcp_toolset ────────────────────────────────────────────────

class TestMakeFilesystemMcpToolset:
    def test_returns_toolset_when_adk_available(self):
        mock_toolset = MagicMock(name="MCPToolset")
        mock_cls = MagicMock(return_value=mock_toolset)
        mock_params = MagicMock(name="StdioServerParameters")

        with patch.dict(
            "sys.modules",
            {
                "google.adk.tools.mcp_tool": MagicMock(
                    MCPToolset=mock_cls,
                    StdioServerParameters=mock_params,
                )
            },
        ):
            result = make_filesystem_mcp_toolset("/data/shared")

        assert result is not None
        mock_cls.assert_called_once()

    def test_returns_none_when_adk_not_available(self):
        with patch(
            "tools.mcp_connector.make_filesystem_mcp_toolset",
            side_effect=lambda path: _simulate_import_error(),
        ):
            pass  # tested inline below

        # Simulate ImportError directly
        # Block the import
        with patch.dict("sys.modules", {"google.adk.tools.mcp_tool": None}):
            result = make_filesystem_mcp_toolset("/data/shared")
        assert result is None

    def test_npx_args_include_path(self):
        captured_params = {}

        def fake_stdio(**kwargs):
            captured_params.update(kwargs)
            return MagicMock()

        def fake_toolset(connection_params):
            return MagicMock()

        mock_module = MagicMock()
        mock_module.StdioServerParameters = fake_stdio
        mock_module.MCPToolset = fake_toolset

        with patch.dict("sys.modules", {"google.adk.tools.mcp_tool": mock_module}):
            make_filesystem_mcp_toolset("/my/path")

        assert captured_params.get("command") == "npx"
        assert "/my/path" in captured_params.get("args", [])


def _simulate_import_error():
    return None


# ── make_sse_mcp_toolset ───────────────────────────────────────────────────────

class TestMakeSseMcpToolset:
    def test_returns_toolset_with_auth_header(self):
        captured_params = {}

        def fake_sse(**kwargs):
            captured_params.update(kwargs)
            return MagicMock()

        def fake_toolset(connection_params):
            return MagicMock()

        mock_module = MagicMock()
        mock_module.SseServerParams = fake_sse
        mock_module.MCPToolset = fake_toolset

        with patch.dict("sys.modules", {"google.adk.tools.mcp_tool": mock_module}):
            make_sse_mcp_toolset("http://mcp.example.com/sse", auth_token="secret-token")

        assert captured_params.get("url") == "http://mcp.example.com/sse"
        assert captured_params.get("headers", {}).get("Authorization") == "Bearer secret-token"

    def test_no_auth_header_when_token_is_none(self):
        captured_params = {}

        def fake_sse(**kwargs):
            captured_params.update(kwargs)
            return MagicMock()

        mock_module = MagicMock()
        mock_module.SseServerParams = fake_sse
        mock_module.MCPToolset = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {"google.adk.tools.mcp_tool": mock_module}):
            make_sse_mcp_toolset("http://mcp.example.com/sse", auth_token=None)

        assert "Authorization" not in captured_params.get("headers", {})

    def test_returns_none_when_adk_not_available(self):
        with patch.dict("sys.modules", {"google.adk.tools.mcp_tool": None}):
            result = make_sse_mcp_toolset("http://mcp.example.com/sse")
        assert result is None


# ── get_configured_mcp_tools ───────────────────────────────────────────────────

class TestGetConfiguredMcpTools:
    def _make_settings(self, fs_path="", sse_url="", sse_token=""):
        s = MagicMock()
        s.mcp_filesystem_path = fs_path
        s.mcp_sse_server_url = sse_url
        s.mcp_sse_auth_token = sse_token
        return s

    def test_returns_empty_list_when_nothing_configured(self):
        settings = self._make_settings()
        result = get_configured_mcp_tools(settings)
        assert result == []

    def test_returns_one_toolset_for_filesystem(self):
        settings = self._make_settings(fs_path="/data")
        mock_toolset = MagicMock(name="fstoolset")
        with patch("tools.mcp_connector.make_filesystem_mcp_toolset", return_value=mock_toolset):
            result = get_configured_mcp_tools(settings)
        assert result == [mock_toolset]

    def test_returns_one_toolset_for_sse(self):
        settings = self._make_settings(sse_url="http://mcp.example.com/sse")
        mock_toolset = MagicMock(name="ssetoolset")
        with patch("tools.mcp_connector.make_sse_mcp_toolset", return_value=mock_toolset):
            result = get_configured_mcp_tools(settings)
        assert result == [mock_toolset]

    def test_returns_two_toolsets_when_both_configured(self):
        settings = self._make_settings(fs_path="/data", sse_url="http://mcp.example.com/sse")
        fs_ts = MagicMock(name="fs")
        sse_ts = MagicMock(name="sse")
        with (
            patch("tools.mcp_connector.make_filesystem_mcp_toolset", return_value=fs_ts),
            patch("tools.mcp_connector.make_sse_mcp_toolset", return_value=sse_ts),
        ):
            result = get_configured_mcp_tools(settings)
        assert fs_ts in result
        assert sse_ts in result
        assert len(result) == 2

    def test_skips_toolset_when_factory_returns_none(self):
        """If an import fails inside the factory, result is None and should be skipped."""
        settings = self._make_settings(fs_path="/data", sse_url="http://mcp.example.com/sse")
        with (
            patch("tools.mcp_connector.make_filesystem_mcp_toolset", return_value=None),
            patch("tools.mcp_connector.make_sse_mcp_toolset", return_value=None),
        ):
            result = get_configured_mcp_tools(settings)
        assert result == []

    def test_passes_auth_token_to_sse_factory(self):
        settings = self._make_settings(sse_url="http://mcp.example.com/sse", sse_token="tok123")
        with patch("tools.mcp_connector.make_sse_mcp_toolset", return_value=MagicMock()) as mock_sse:
            get_configured_mcp_tools(settings)
        mock_sse.assert_called_once_with("http://mcp.example.com/sse", auth_token="tok123")
