"""
tests/memory/test_context_budget.py

Unit tests for memory.context_budget — fully offline, no GCP required.
"""
from __future__ import annotations



def _make_skill(skill_id: str, trigger: str = "some trigger", steps: int = 3):
    from memory.skill_models import Skill
    return Skill(
        skill_id=skill_id,
        agent_name="TestAgent",
        domain="test",
        trigger=trigger,
        procedure=[f"Step {i}" for i in range(1, steps + 1)],
        example_query="",
    )


def _make_profile(user_id: str = "u1", name: str = "Alice", role: str = "Engineer"):
    from memory.user_profile import UserProfile
    return UserProfile(user_id=user_id, name=name, role=role)


class TestPrioritiseMemory:
    def test_returns_all_when_within_budget(self):
        from memory.context_budget import prioritise_memory, _SKILL_TOKEN_ESTIMATE
        skills = [_make_skill(f"s{i}") for i in range(3)]
        result = prioritise_memory(skills, budget=_SKILL_TOKEN_ESTIMATE * 10)
        assert result == skills

    def test_trims_when_over_budget(self):
        from memory.context_budget import prioritise_memory, _SKILL_TOKEN_ESTIMATE
        skills = [_make_skill(f"s{i}") for i in range(5)]
        result = prioritise_memory(skills, budget=_SKILL_TOKEN_ESTIMATE * 2)
        assert len(result) == 2

    def test_returns_empty_for_zero_budget(self):
        from memory.context_budget import prioritise_memory
        skills = [_make_skill("s1")]
        result = prioritise_memory(skills, budget=0)
        assert result == []

    def test_returns_empty_for_empty_input(self):
        from memory.context_budget import prioritise_memory
        result = prioritise_memory([], budget=5000)
        assert result == []

    def test_preserves_priority_order(self):
        from memory.context_budget import prioritise_memory, _SKILL_TOKEN_ESTIMATE
        skills = [_make_skill(f"s{i}") for i in range(5)]
        result = prioritise_memory(skills, budget=_SKILL_TOKEN_ESTIMATE * 3)
        assert [s.skill_id for s in result] == ["s0", "s1", "s2"]


class TestBuildContextSummary:
    def test_includes_profile_tier1(self):
        from memory.context_budget import build_context_summary
        profile = _make_profile()
        summary = build_context_summary(profile, [], budget_tokens=5000)
        assert "Alice" in summary
        assert "USER CONTEXT" in summary

    def test_includes_skills_tier2(self):
        from memory.context_budget import build_context_summary
        skills = [_make_skill("test-skill", trigger="When user asks about test")]
        summary = build_context_summary(None, skills, budget_tokens=5000)
        assert "test-skill" in summary
        assert "RELEVANT SKILLS" in summary

    def test_profile_and_skills_combined(self):
        from memory.context_budget import build_context_summary
        profile = _make_profile()
        skills = [_make_skill("s1")]
        summary = build_context_summary(profile, skills, budget_tokens=5000)
        assert "USER CONTEXT" in summary
        assert "RELEVANT SKILLS" in summary

    def test_returns_empty_string_when_nothing_fits(self):
        from memory.context_budget import build_context_summary
        profile = _make_profile()
        skills = [_make_skill("s1")]
        summary = build_context_summary(profile, skills, budget_tokens=1)
        assert summary == ""

    def test_skills_trimmed_to_budget(self):
        from memory.context_budget import build_context_summary, _SKILL_TOKEN_ESTIMATE
        skills = [_make_skill(f"s{i}") for i in range(10)]
        summary = build_context_summary(None, skills, budget_tokens=_SKILL_TOKEN_ESTIMATE * 2)
        assert "s0" in summary
        assert "s9" not in summary

    def test_none_profile_skipped_gracefully(self):
        from memory.context_budget import build_context_summary
        skills = [_make_skill("s1")]
        summary = build_context_summary(None, skills, budget_tokens=5000)
        assert "USER CONTEXT" not in summary
        assert "s1" in summary

    def test_empty_skills_list(self):
        from memory.context_budget import build_context_summary
        profile = _make_profile()
        summary = build_context_summary(profile, [], budget_tokens=5000)
        assert "RELEVANT SKILLS" not in summary
        assert "Alice" in summary
