"""
tests/agents/test_scoped_instructions.py

Unit tests for agents/scoped_instructions.py — hierarchical AGENTS.md loader.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agents.scoped_instructions import (
    _filter_scoped_blocks,
    _merge_layers,
    load_scope_tree,
    resolve_instructions,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))
    return p


# ── _filter_scoped_blocks ─────────────────────────────────────────────────────


def test_scoped_block_included_for_matching_agent():
    text = "Global line.\n## SCOPED: AnalyticsAgent\nAnalytics-only line.\n"
    result = _filter_scoped_blocks(text, "AnalyticsAgent")
    assert "Analytics-only line." in result
    assert "## SCOPED" not in result


def test_scoped_block_excluded_for_other_agent():
    text = "Global line.\n## SCOPED: HRAgent\nHR-only line.\n"
    result = _filter_scoped_blocks(text, "AnalyticsAgent")
    assert "HR-only line." not in result
    assert "Global line." in result


def test_multiple_scoped_blocks():
    text = (
        "Shared.\n"
        "## SCOPED: AnalyticsAgent\nA line.\n"
        "## SCOPED: HRAgent\nH line.\n"
        "## Normal Section\nshared section.\n"
    )
    result = _filter_scoped_blocks(text, "AnalyticsAgent")
    assert "A line." in result
    assert "H line." not in result
    assert "shared section." in result


def test_scoped_case_insensitive():
    text = "## SCOPED: analyticsagent\nLower line.\n"
    result = _filter_scoped_blocks(text, "AnalyticsAgent")
    assert "Lower line." in result


# ── _merge_layers ─────────────────────────────────────────────────────────────


def test_merge_appends_by_default():
    result = _merge_layers(["Base instruction.", "Domain extension."])
    assert "Base instruction." in result
    assert "Domain extension." in result


def test_merge_extends_marker_stripped():
    result = _merge_layers(["Base.", "## EXTENDS\nChild text."])
    assert "## EXTENDS" not in result
    assert "Child text." in result


def test_merge_override_replaces_section():
    parent = "## Overview\nOld overview.\n## Details\nOld details.\n"
    child = "## OVERRIDES\n## Overview\nNew overview.\n"
    result = _merge_layers([parent, child])
    assert "New overview." in result
    assert "Old overview." not in result
    assert "Old details." in result  # unaffected section preserved


def test_merge_override_appends_new_section():
    parent = "## Overview\nExisting.\n"
    child = "## OVERRIDES\n## NewSection\nBrand new.\n"
    result = _merge_layers([parent, child])
    assert "Existing." in result
    assert "Brand new." in result


def test_merge_empty_child_skipped():
    result = _merge_layers(["Base.", "", "   "])
    assert result.strip() == "Base."


def test_merge_three_layers():
    layers = ["Root.", "Domain.", "AgentSpecific."]
    result = _merge_layers(layers)
    for text in layers:
        assert text in result


# ── resolve_instructions ──────────────────────────────────────────────────────


def test_resolve_root_only(tmp_path):
    _write(tmp_path, "AGENTS.md", "Root instruction.\n")
    result = resolve_instructions("AnalyticsAgent", root=tmp_path)
    assert "Root instruction." in result


def test_resolve_domain_appended(tmp_path):
    _write(tmp_path, "AGENTS.md", "Root.\n")
    _write(tmp_path, "agents/AGENTS.md", "Domain.\n")
    result = resolve_instructions(
        "AnalyticsAgent", root=tmp_path, domain_path=tmp_path / "agents"
    )
    assert "Root." in result
    assert "Domain." in result


def test_resolve_agent_path_appended(tmp_path):
    _write(tmp_path, "AGENTS.md", "Root.\n")
    _write(tmp_path, "agents/analytics/AGENTS.md", "AgentSpecific.\n")
    result = resolve_instructions(
        "AnalyticsAgent",
        root=tmp_path,
        agent_path=tmp_path / "agents" / "analytics",
    )
    assert "Root." in result
    assert "AgentSpecific." in result


def test_resolve_missing_files_return_empty(tmp_path):
    result = resolve_instructions("AnalyticsAgent", root=tmp_path)
    assert result == ""


def test_resolve_scoped_block_filtered(tmp_path):
    _write(
        tmp_path,
        "AGENTS.md",
        "Global.\n## SCOPED: HRAgent\nHR only.\n",
    )
    result = resolve_instructions("AnalyticsAgent", root=tmp_path)
    assert "Global." in result
    assert "HR only." not in result


def test_resolve_override_in_domain(tmp_path):
    _write(tmp_path, "AGENTS.md", "## Overview\nRoot overview.\n")
    _write(
        tmp_path,
        "agents/AGENTS.md",
        "## OVERRIDES\n## Overview\nDomain override.\n",
    )
    result = resolve_instructions(
        "AnalyticsAgent", root=tmp_path, domain_path=tmp_path / "agents"
    )
    assert "Domain override." in result
    assert "Root overview." not in result


# ── load_scope_tree ───────────────────────────────────────────────────────────


def test_load_scope_tree(tmp_path):
    _write(tmp_path, "AGENTS.md", "root")
    _write(tmp_path, "agents/AGENTS.md", "d1")
    _write(tmp_path, "agents/analytics/AGENTS.md", "d2")
    tree = load_scope_tree(root=tmp_path)
    assert "root" in tree
    assert len(tree["root"]) == 1
    assert "depth1" in tree
    assert "depth2" in tree


def test_load_scope_tree_ignores_git(tmp_path):
    _write(tmp_path, "AGENTS.md", "root")
    _write(tmp_path, ".git/AGENTS.md", "git")
    tree = load_scope_tree(root=tmp_path)
    all_paths = [str(p) for paths in tree.values() for p in paths]
    assert not any(".git" in p for p in all_paths)
