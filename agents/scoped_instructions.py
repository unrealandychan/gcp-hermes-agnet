"""
agents/scoped_instructions.py

Hierarchical AGENTS.md / scoped instruction loader.

Resolves agent instructions from a hierarchy of AGENTS.md files, starting at
the project root and descending into domain-specific subdirectories.  Each
subdirectory's AGENTS.md can *extend* or *override* the parent instructions.

Resolution order (highest priority last — later entries win on override):
  1. Project root AGENTS.md      (global baseline)
  2. Domain subdirectory AGENTS.md  (e.g. agents/AGENTS.md, memory/AGENTS.md)
  3. Agent-specific AGENTS.md    (e.g. agents/analytics/AGENTS.md)

Override syntax in AGENTS.md
─────────────────────────────
  ## EXTENDS
  Appended to parent instructions (default — no marker needed).

  ## OVERRIDES
  Replaces the parent section that follows the marker.
  Subsequent lines (until the next ## heading) fully replace the matching
  parent section with the same heading title.

  ## SCOPED: <AgentName>
  Instructions in this block are injected ONLY into the named agent.

Usage
─────
    from agents.scoped_instructions import resolve_instructions

    instruction = resolve_instructions(
        agent_name="AnalyticsAgent",
        root=Path("/project"),
        domain_path=Path("/project/agents"),
    )
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_AGENTS_MD = "AGENTS.md"
_OVERRIDE_MARKER = re.compile(r"^##\s+OVERRIDES?\s*$", re.IGNORECASE | re.MULTILINE)
_SCOPED_MARKER = re.compile(r"^##\s+SCOPED:\s*(\w+)\s*$", re.IGNORECASE | re.MULTILINE)
_EXTENDS_MARKER = re.compile(r"^##\s+EXTENDS?\s*$", re.IGNORECASE | re.MULTILINE)
_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)


# ── Public API ────────────────────────────────────────────────────────────────


def resolve_instructions(
    agent_name: str,
    root: Path | None = None,
    domain_path: Path | None = None,
    agent_path: Path | None = None,
) -> str:
    """
    Return the merged instruction string for *agent_name*.

    Args:
        agent_name: The agent's name (used to filter ## SCOPED: blocks).
        root:        Project root directory (contains the global AGENTS.md).
                     Defaults to the directory containing this file's grandparent.
        domain_path: Directory for the domain sub-section (e.g. agents/).
        agent_path:  Agent-specific sub-directory (deepest level).

    Returns:
        Merged instruction text, or "" if no AGENTS.md files are found.
    """
    if root is None:
        root = Path(__file__).parent.parent  # project root

    layers: list[str] = []

    # Layer 1 — project root
    layers.append(_read_relevant(root / _AGENTS_MD, agent_name))

    # Layer 2 — domain subdirectory
    if domain_path is not None:
        layers.append(_read_relevant(domain_path / _AGENTS_MD, agent_name))

    # Layer 3 — agent-specific directory
    if agent_path is not None:
        layers.append(_read_relevant(agent_path / _AGENTS_MD, agent_name))

    return _merge_layers(layers)


def load_scope_tree(root: Path | None = None) -> dict[str, list[Path]]:
    """
    Scan *root* recursively and return a mapping of AGENTS.md files grouped
    by depth.  Useful for debugging the resolution chain.

    Returns:
        {depth_label: [Path, ...]}  e.g. {"root": [...], "depth1": [...], ...}
    """
    if root is None:
        root = Path(__file__).parent.parent

    tree: dict[str, list[Path]] = {}
    for path in sorted(root.rglob(_AGENTS_MD)):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        depth = len(path.relative_to(root).parts) - 1
        key = "root" if depth == 0 else f"depth{depth}"
        tree.setdefault(key, []).append(path)
    return tree


# ── Internals ─────────────────────────────────────────────────────────────────


def _read_relevant(path: Path, agent_name: str) -> str:
    """
    Read *path*, strip any ## SCOPED blocks that are NOT for *agent_name*,
    include blocks that ARE for *agent_name* (with the marker stripped).
    """
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read %s", path)
        return ""

    return _filter_scoped_blocks(text, agent_name)


def _filter_scoped_blocks(text: str, agent_name: str) -> str:
    """
    Remove ## SCOPED: <Other> blocks and unwrap ## SCOPED: <agent_name> blocks
    (keep content, strip the marker heading).
    """
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        m = _SCOPED_MARKER.match(lines[i])
        if m:
            block_agent = m.group(1).strip()
            # Collect until next ## heading or EOF
            i += 1
            block: list[str] = []
            while i < len(lines) and not re.match(r"^##\s+", lines[i]):
                block.append(lines[i])
                i += 1
            if block_agent.lower() == agent_name.lower():
                result.extend(block)
            # else: discard the scoped block
        else:
            result.append(lines[i])
            i += 1
    return "".join(result)


def _merge_layers(layers: list[str]) -> str:
    """
    Merge a list of text layers (root → domain → agent-specific).

    Rules:
    - Default (no marker): the child text is *appended* to the parent.
    - ## OVERRIDES marker: the block *following* the marker replaces the
      matching parent section (by heading title).
    - ## EXTENDS marker: explicitly requests append (same as default, but
      strips the marker heading from the output).
    """
    merged = layers[0] if layers else ""
    for child in layers[1:]:
        if not child.strip():
            continue
        if _OVERRIDE_MARKER.search(child):
            merged = _apply_overrides(merged, child)
        else:
            # Strip ## EXTENDS marker if present before appending
            child_clean = _EXTENDS_MARKER.sub("", child).strip()
            if child_clean:
                merged = merged.rstrip() + "\n\n" + child_clean
    return merged.strip()


def _apply_overrides(parent: str, child: str) -> str:
    """
    Apply ## OVERRIDES sections from *child* onto *parent*.

    Each section in *child* after ## OVERRIDES replaces the corresponding
    section in *parent* that has the same ## heading title.  Sections not
    present in *parent* are appended.
    """
    # Split child at ## OVERRIDES marker
    parts = _OVERRIDE_MARKER.split(child, maxsplit=1)
    preamble = parts[0].strip()  # anything before ## OVERRIDES
    override_text = parts[1] if len(parts) > 1 else ""

    # Parse override_text into {heading: content} sections
    override_sections = _parse_sections(override_text)

    # Parse parent into sections preserving order
    parent_sections = _parse_sections(parent)

    # Apply overrides
    result_sections: dict[str, str] = dict(parent_sections)
    for heading, content in override_sections.items():
        result_sections[heading] = content

    # Reconstruct: keep parent order, append new sections from child
    out_parts: list[str] = []
    seen: set[str] = set()

    for heading, _ in parent_sections.items():
        out_parts.append(f"## {heading}\n{result_sections[heading]}")
        seen.add(heading)

    for heading, content in override_sections.items():
        if heading not in seen:
            out_parts.append(f"## {heading}\n{content}")

    # Include preamble (content before any ## headings in parent)
    reconstructed = "\n\n".join(out_parts)
    if preamble:
        reconstructed = preamble + "\n\n" + reconstructed

    return reconstructed.strip()


def _parse_sections(text: str) -> dict[str, str]:
    """
    Split *text* into an ordered dict of {heading_title: section_body}.
    Content before the first heading is stored under key "" (empty string).
    """
    sections: dict[str, str] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        m = _HEADING.match(line)
        if m:
            sections[current_heading] = "".join(current_lines)
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_heading] = "".join(current_lines)
    return sections
