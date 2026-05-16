"""
tests/agents/test_agent_loader.py

Unit tests for agents/loader.py — fully offline, no GCP required.
All heavy deps are stubbed by tests/conftest.py.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_settings(model: str = "gemini-2.0-flash"):
    s = MagicMock()
    s.agent_model_orchestrator = model
    s.agent_model_analytics = model
    s.agent_model_hr = model
    s.agent_model_it_helpdesk = model
    s.agent_model_developer = model
    s.agent_model_task_planner = model
    s.agent_model_task_executor = model
    s.agent_model_skill_extractor = model
    s.knowledge_corpus_name = ""
    s.skills_corpus_name = ""
    s.mcp_filesystem_path = ""
    s.mcp_sse_server_url = ""
    s.mcp_sse_auth_token = ""
    s.model_armor_template_id = ""
    s.gcp_project_id = "test-project"
    s.gcp_location = "us-central1"
    return s


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "agents.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


MINIMAL_YAML = """\
    agents:
      - name: TestAgent
        description: "A test agent"
        model: gemini-2.0-flash
        tools: [search]
    """

TWO_AGENTS_YAML = """\
    agents:
      - name: AgentA
        description: "First agent"
        model: gemini-2.0-flash
        tools: []

      - name: AgentB
        description: "Second agent"
        model: gemini-2.0-flash
        tools: []
    """

ENV_VAR_YAML = """\
    agents:
      - name: EnvAgent
        description: "Uses env var for model"
        model: ${TEST_MODEL_VAR:-gemini-1.5-flash}
        tools: []
    """

MISSING_NAME_YAML = """\
    agents:
      - description: "No name field"
        model: gemini-2.0-flash
        tools: []
    """

UNKNOWN_TOOL_YAML = """\
    agents:
      - name: ToolAgent
        description: "Has unknown tool"
        model: gemini-2.0-flash
        tools: [nonexistent_tool]
    """

INVALID_YAML = """\
    agents: not_a_list
    """


_COMMON_PATCHES = [
    patch("models.provider.get_model", return_value="gemini-2.0-flash"),
    patch("tools.bigquery_tool.make_bigquery_tool", return_value=MagicMock(name="bq")),
    patch("tools.search_tool.make_search_tool", return_value=MagicMock(name="search")),
    patch("tools.storage_tool.make_storage_tool", return_value=MagicMock(name="storage")),
    patch("memory.skill_learning.build_skill_learning_callback", return_value=None),
]


def _start(patches):
    for p in patches:
        p.start()
    return patches


def _stop(patches):
    for p in patches:
        p.stop()


# ── load_agents_yaml ──────────────────────────────────────────────────────────

class TestLoadAgentsYaml:
    def test_parses_minimal_yaml(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        from agents.loader import load_agents_yaml
        agents = load_agents_yaml(path)
        assert len(agents) == 1
        assert agents[0]["name"] == "TestAgent"

    def test_resolves_env_var_with_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TEST_MODEL_VAR", raising=False)
        path = _write_yaml(tmp_path, ENV_VAR_YAML)
        from agents.loader import load_agents_yaml
        agents = load_agents_yaml(path)
        assert agents[0]["model"] == "gemini-1.5-flash"

    def test_resolves_env_var_from_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_MODEL_VAR", "gemini-2.0-pro")
        path = _write_yaml(tmp_path, ENV_VAR_YAML)
        from agents.loader import load_agents_yaml
        agents = load_agents_yaml(path)
        assert agents[0]["model"] == "gemini-2.0-pro"

    def test_raises_for_invalid_structure(self, tmp_path):
        path = _write_yaml(tmp_path, INVALID_YAML)
        from agents.loader import load_agents_yaml
        with pytest.raises(ValueError, match="top-level 'agents' list"):
            load_agents_yaml(path)


# ── build_agents_from_yaml ─────────────────────────────────────────────────────

class TestBuildAgentsFromYaml:
    def setup_method(self):
        self._patches = _start(list(_COMMON_PATCHES))

    def teardown_method(self):
        _stop(self._patches)

    def test_builds_generic_agents(self, tmp_path):
        path = _write_yaml(tmp_path, TWO_AGENTS_YAML)
        from agents.loader import build_agents_from_yaml
        agents = build_agents_from_yaml(_mock_settings(), yaml_path=path)
        assert len(agents) == 2
        names = [a.name for a in agents]
        assert "AgentA" in names
        assert "AgentB" in names

    def test_skips_entry_with_no_name(self, tmp_path, caplog):
        import logging
        path = _write_yaml(tmp_path, MISSING_NAME_YAML)
        from agents.loader import build_agents_from_yaml
        with caplog.at_level(logging.WARNING):
            agents = build_agents_from_yaml(_mock_settings(), yaml_path=path)
        assert agents == []
        assert "no 'name'" in caplog.text

    def test_unknown_tool_is_skipped_with_warning(self, tmp_path, caplog):
        import logging
        path = _write_yaml(tmp_path, UNKNOWN_TOOL_YAML)
        from agents.loader import build_agents_from_yaml
        with caplog.at_level(logging.WARNING):
            agents = build_agents_from_yaml(_mock_settings(), yaml_path=path)
        # Agent still built, just without the unknown tool
        assert len(agents) == 1
        assert "nonexistent_tool" in caplog.text

    def test_uses_custom_builder_for_known_agents(self, tmp_path):
        yaml_content = """\
            agents:
              - name: AnalyticsAgent
                description: "Analytics"
                model: gemini-2.0-flash
                tools: [bigquery, search]
            """
        path = _write_yaml(tmp_path, yaml_content)

        fake_agent = MagicMock()
        fake_agent.name = "AnalyticsAgent"
        with patch("agents.analytics.build_analytics_agent", return_value=fake_agent) as mock_builder:
            from agents.loader import build_agents_from_yaml
            agents = build_agents_from_yaml(_mock_settings(), yaml_path=path)
        mock_builder.assert_called_once()
        assert agents[0] is fake_agent
