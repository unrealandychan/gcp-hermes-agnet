"""
tests/agents/test_agent_builds.py

Smoke tests — verify every agent builder function returns an LlmAgent
with the expected name, tools, and sub-agents without making any network
or LLM calls.

All GCP / ADK services are patched at the module level via conftest.py
stubs.  Individual test classes use fresh patch objects per method to
avoid the "Patch is already started" issue with shared patch lists.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_settings(
    model: str = "gemini-2.5-flash",
    *,
    mcp_filesystem_path: str = "",
    mcp_sse_server_url: str = "",
    model_armor_template_id: str = "",
):
    s = MagicMock()
    s.agent_model_orchestrator = model
    s.agent_model_analytics = model
    s.agent_model_hr = model
    s.agent_model_it_helpdesk = model
    s.agent_model_developer = model
    s.agent_model_task_planner = model
    s.agent_model_task_executor = model
    s.agent_model_skill_extractor = model
    s.mcp_filesystem_path = mcp_filesystem_path
    s.mcp_sse_server_url = mcp_sse_server_url
    s.model_armor_template_id = model_armor_template_id
    s.gcp_project_id = "test-project"
    s.gcp_location = "us-central1"
    s.knowledge_corpus_name = ""
    s.skills_corpus_name = ""
    return s


def _patch_all():
    """Return a fresh dict of patch objects — call start/stop per test."""
    return [
        patch("models.provider.get_model", return_value="gemini-2.5-flash"),
        patch("tools.bigquery_tool.make_bigquery_tool", return_value=MagicMock(name="bq")),
        patch("tools.search_tool.make_search_tool", return_value=MagicMock(name="search")),
        patch("tools.storage_tool.make_storage_tool", return_value=MagicMock(name="storage")),
        patch("memory.skill_learning.build_skill_learning_callback", return_value=None),
    ]


def _start(patches):
    for p in patches:
        p.start()


def _stop(patches):
    for p in patches:
        p.stop()


class TestAnalyticsAgentBuild:
    def setup_method(self):
        self._patches = _patch_all()
        _start(self._patches)

    def teardown_method(self):
        _stop(self._patches)

    def test_returns_llm_agent_with_correct_name(self):
        from agents.analytics import build_analytics_agent
        agent = build_analytics_agent(_mock_settings())
        assert agent.name == "AnalyticsAgent"

    def test_no_google_search_in_tools(self):
        # google_search (grounding) must NOT be mixed with other FunctionTools —
        # Gemini API raises 400 INVALID_ARGUMENT: "Multiple tools are supported
        # only when they are all search tools."
        from agents.analytics import build_analytics_agent
        agent = build_analytics_agent(_mock_settings())
        assert not any("google_search" in str(t) for t in (agent.tools or []))


class TestHrAgentBuild:
    def setup_method(self):
        self._patches = _patch_all()
        _start(self._patches)

    def teardown_method(self):
        _stop(self._patches)

    def test_returns_llm_agent_with_correct_name(self):
        from agents.hr import build_hr_agent
        agent = build_hr_agent(_mock_settings())
        assert agent.name == "HRAgent"

    def test_has_multiple_tools(self):
        from agents.hr import build_hr_agent
        agent = build_hr_agent(_mock_settings())
        assert agent.tools is not None
        assert len(agent.tools) > 3


class TestItHelpdeskAgentBuild:
    def setup_method(self):
        self._patches = _patch_all()
        _start(self._patches)

    def teardown_method(self):
        _stop(self._patches)

    def test_returns_llm_agent_with_correct_name(self):
        from agents.it_helpdesk import build_it_helpdesk_agent
        agent = build_it_helpdesk_agent(_mock_settings())
        assert agent.name == "ITHelpdeskAgent"

    def test_no_google_search_in_tools(self):
        # google_search must NOT be mixed with other FunctionTools
        from agents.it_helpdesk import build_it_helpdesk_agent
        agent = build_it_helpdesk_agent(_mock_settings())
        assert not any("google_search" in str(t) for t in (agent.tools or []))


class TestDeveloperAgentBuild:
    def setup_method(self):
        self._patches = _patch_all()
        _start(self._patches)

    def teardown_method(self):
        _stop(self._patches)

    def test_returns_llm_agent_with_correct_name(self):
        from agents.developer import build_developer_agent
        agent = build_developer_agent(_mock_settings())
        assert agent.name == "DeveloperAgent"

    def test_description_mentions_sandbox(self):
        from agents.developer import build_developer_agent
        agent = build_developer_agent(_mock_settings())
        assert "sandbox" in agent.description.lower()

    def test_no_google_search_in_tools(self):
        # google_search must NOT be mixed with other FunctionTools
        from agents.developer import build_developer_agent
        agent = build_developer_agent(_mock_settings())
        assert not any("google_search" in str(t) for t in (agent.tools or []))


class TestOrchestratorBuild:
    def setup_method(self):
        self._patches = _patch_all()
        _start(self._patches)

    def teardown_method(self):
        _stop(self._patches)

    def test_returns_llm_agent_with_correct_name(self):
        from agents.orchestrator import build_orchestrator
        agent = build_orchestrator(_mock_settings())
        assert agent.name == "Orchestrator"

    def test_has_sub_agents(self):
        from agents.orchestrator import build_orchestrator
        agent = build_orchestrator(_mock_settings())
        # Sub-agents are loaded from agents.yaml — at least the built-in ones
        assert len(agent.sub_agents) >= 4

    def test_has_no_tools(self):
        # Orchestrator is a pure routing agent — no tools, only sub_agents.
        # google_search was removed because Vertex AI raises 400 INVALID_ARGUMENT
        # when any agent mixes search tools with sub_agents or function tools.
        from agents.orchestrator import build_orchestrator
        agent = build_orchestrator(_mock_settings())
        assert not agent.tools

