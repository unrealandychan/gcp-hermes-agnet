"""
tests/memory/test_skill_loader.py

Unit tests for memory.skill_loader — fully offline, no GCP required.
"""
from __future__ import annotations

import textwrap
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


VALID_SKILL = """\
    ---
    name: test-skill
    description: "A test skill"
    agent_name: AnalyticsAgent
    trigger: "When the user asks about tests"
    tags: [test]
    version: 1.0.0
    ---

    # Test Skill

    ## Steps
    1. Do the first thing
    2. Do the second thing
    3. Confirm with the user
    """

VALID_SKILL_NO_STEPS = """\
    ---
    name: no-steps-skill
    description: "A skill without a steps section"
    agent_name: HRAgent
    trigger: "When no steps are needed"
    ---

    Just some description text, no numbered list.
    """

MISSING_REQUIRED = """\
    ---
    description: "Missing name and agent_name"
    trigger: "Some trigger"
    ---

    Body text.
    """

NO_FRONTMATTER = """\
    # Just a README

    This file has no YAML frontmatter.
    """

INVALID_YAML = """\
    ---
    name: bad
    description: [unclosed
    ---

    Body.
    """


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestLoadSkillsFromDir:
    def test_loads_valid_skill(self, tmp_path):
        _write(tmp_path, "test-skill.md", VALID_SKILL)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert len(skills) == 1
        s = skills[0]
        assert s.skill_id == "test-skill"
        assert s.agent_name == "AnalyticsAgent"
        assert s.trigger == "When the user asks about tests"

    def test_extracts_procedure_steps(self, tmp_path):
        _write(tmp_path, "test-skill.md", VALID_SKILL)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert skills[0].procedure == [
            "Do the first thing",
            "Do the second thing",
            "Confirm with the user",
        ]

    def test_empty_procedure_when_no_steps_section(self, tmp_path):
        _write(tmp_path, "no-steps.md", VALID_SKILL_NO_STEPS)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert len(skills) == 1
        assert skills[0].procedure == []

    def test_skips_template_md(self, tmp_path):
        _write(tmp_path, "TEMPLATE.md", VALID_SKILL)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert skills == []

    def test_skips_no_frontmatter_files(self, tmp_path):
        _write(tmp_path, "README.md", NO_FRONTMATTER)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert skills == []

    def test_skips_missing_required_fields_with_warning(self, tmp_path, caplog):
        import logging
        _write(tmp_path, "bad-skill.md", MISSING_REQUIRED)
        from memory.skill_loader import load_skills_from_dir
        with caplog.at_level(logging.WARNING):
            skills = load_skills_from_dir(tmp_path)
        assert skills == []
        assert "missing required" in caplog.text.lower() or "failed to parse" in caplog.text.lower()

    def test_skips_invalid_yaml_with_warning(self, tmp_path, caplog):
        import logging
        _write(tmp_path, "invalid.md", INVALID_YAML)
        from memory.skill_loader import load_skills_from_dir
        with caplog.at_level(logging.WARNING):
            skills = load_skills_from_dir(tmp_path)
        assert skills == []

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path / "does_not_exist")
        assert skills == []

    def test_loads_multiple_skills(self, tmp_path):
        _write(tmp_path, "skill-a.md", VALID_SKILL)
        _write(tmp_path, "skill-b.md", VALID_SKILL_NO_STEPS)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert len(skills) == 2

    def test_recurses_into_subdirectories(self, tmp_path):
        sub = tmp_path / "examples"
        sub.mkdir()
        _write(sub, "nested-skill.md", VALID_SKILL)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert len(skills) == 1

    def test_domain_inferred_from_agent_name(self, tmp_path):
        _write(tmp_path, "test-skill.md", VALID_SKILL)
        from memory.skill_loader import load_skills_from_dir
        skills = load_skills_from_dir(tmp_path)
        assert skills[0].domain == "analytics"
