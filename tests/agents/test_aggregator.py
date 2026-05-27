"""
tests/agents/test_aggregator.py

Unit tests for AggregatorAgent and the SequentialPipeline integration
in build_task_agent / build_dynamic_parallel_dispatcher.
"""
from __future__ import annotations

import pytest

from agents.aggregator import build_aggregator_agent
from agents.task_agent import build_task_agent, build_dynamic_parallel_dispatcher
from config import Settings


@pytest.fixture()
def settings():
    return Settings(
        google_cloud_project="test-project",
        google_cloud_location="us-central1",
    )


# ─── AggregatorAgent ──────────────────────────────────────────────────────────


class TestBuildAggregatorAgent:
    def test_returns_llm_agent(self, settings):
        agent = build_aggregator_agent(settings)
        assert agent.name == "AggregatorAgent"

    def test_has_description(self, settings):
        agent = build_aggregator_agent(settings)
        assert "synthesises" in agent.description.lower() or "consolidates" in agent.description.lower()

    def test_no_tools(self, settings):
        """AggregatorAgent should not have external tools — it only reads context."""
        agent = build_aggregator_agent(settings)
        assert not agent.tools


# ─── build_task_agent — SequentialPipeline integration ───────────────────────


class TestBuildTaskAgentSequentialPipeline:
    def test_first_sub_agent_is_sequential_pipeline(self, settings):
        agent = build_task_agent(settings, specialist_agents=[])
        pipeline = agent.sub_agents[0]
        assert pipeline.name == "SequentialPipeline"

    def test_sequential_pipeline_has_two_children(self, settings):
        agent = build_task_agent(settings, specialist_agents=[])
        pipeline = agent.sub_agents[0]
        assert len(pipeline.sub_agents) == 2

    def test_pipeline_first_child_is_parallel_dispatcher(self, settings):
        agent = build_task_agent(settings, specialist_agents=[])
        pipeline = agent.sub_agents[0]
        dispatcher = pipeline.sub_agents[0]
        assert dispatcher.name == "ParallelDispatcher"

    def test_pipeline_second_child_is_aggregator(self, settings):
        agent = build_task_agent(settings, specialist_agents=[])
        pipeline = agent.sub_agents[0]
        aggregator = pipeline.sub_agents[1]
        assert aggregator.name == "AggregatorAgent"

    def test_parallel_dispatcher_has_four_specialists(self, settings):
        agent = build_task_agent(settings, specialist_agents=[])
        pipeline = agent.sub_agents[0]
        dispatcher = pipeline.sub_agents[0]
        assert len(dispatcher.sub_agents) == 4

    def test_specialist_agents_appended_for_sequential_fallback(self, settings):
        from tests.conftest import _FakeLlmAgent
        fake = _FakeLlmAgent(name="FakeSpecialist")
        agent = build_task_agent(settings, specialist_agents=[fake])
        # sub_agents = [SequentialPipeline, FakeSpecialist]
        assert len(agent.sub_agents) == 2
        assert agent.sub_agents[1].name == "FakeSpecialist"

    def test_no_specialist_agents_defaults_to_pipeline_only(self, settings):
        """ADK 2.0: specialist_agents=None should work (defaults to empty)."""
        agent = build_task_agent(settings)
        # sub_agents = [SequentialPipeline] only
        assert agent.sub_agents[0].name == "SequentialPipeline"


# ─── build_dynamic_parallel_dispatcher — returns SequentialAgent ─────────────


class TestBuildDynamicParallelDispatcher:
    def test_returns_none_when_no_agents_synthesised(self, settings, monkeypatch):
        import agents.task_agent as ta

        monkeypatch.setattr(
            "agents.synthesizer.AgentSynthesizer",
            type("_S", (), {"__init__": lambda s, _: None,
                             "synthesise": lambda s, t, seq=0: []})
        )
        pipeline, seq = ta.build_dynamic_parallel_dispatcher(settings, "irrelevant")
        assert pipeline is None
        assert seq == []

    def test_returns_sequential_pipeline_when_agents_found(self, settings, monkeypatch):
        from tests.conftest import _FakeLlmAgent

        fake_agent = _FakeLlmAgent(name="SynthAgent")

        class _FakeSynth:
            def __init__(self, _): pass
            def synthesise(self, _, seq=0): return [fake_agent]

        monkeypatch.setattr("agents.synthesizer.AgentSynthesizer", _FakeSynth)

        pipeline, seq = build_dynamic_parallel_dispatcher(settings, "some task")
        assert pipeline is not None
        assert pipeline.name == "DynamicSequentialPipeline"

    def test_dynamic_pipeline_ends_with_aggregator(self, settings, monkeypatch):
        from tests.conftest import _FakeLlmAgent

        fake_agent = _FakeLlmAgent(name="SynthAgent")

        class _FakeSynth:
            def __init__(self, _): pass
            def synthesise(self, _, seq=0): return [fake_agent]

        monkeypatch.setattr("agents.synthesizer.AgentSynthesizer", _FakeSynth)

        pipeline, _ = build_dynamic_parallel_dispatcher(settings, "some task")
        aggregator = pipeline.sub_agents[-1]
        assert aggregator.name == "AggregatorAgent"
