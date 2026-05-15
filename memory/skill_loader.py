"""
memory/skill_loader.py

Loads human-readable skill files (skills/*.md) from the local filesystem
into Skill objects compatible with SkillStore.

File format: YAML frontmatter (between --- delimiters) + Markdown body.

Required frontmatter fields:
  name         - unique skill identifier (slug)
  description  - one-sentence description
  agent_name   - which agent this skill belongs to
  trigger      - when to apply this skill (one sentence)

Optional frontmatter fields:
  tags         - list of strings
  version      - semver string (default: "1.0.0")
  author       - string
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterator

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from memory.skill_models import Skill

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Default skills directory relative to the project root
_DEFAULT_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skills_from_dir(
    skills_dir: str | Path | None = None,
) -> list[Skill]:
    """
    Scan *skills_dir* for ``*.md`` files and parse each one into a Skill.

    Files that fail to parse are skipped with a warning.
    ``TEMPLATE.md`` is always skipped.

    Args:
        skills_dir: Path to the skills directory.  Defaults to ``skills/``
                    at the project root.

    Returns:
        List of parsed Skill objects (may be empty if no valid files found).
    """
    target = Path(skills_dir) if skills_dir else _DEFAULT_SKILLS_DIR

    if not target.exists():
        logger.warning("Skills directory does not exist: %s", target)
        return []

    skills: list[Skill] = []
    for path in _iter_skill_files(target):
        try:
            skill = _parse_skill_file(path)
            if skill:
                skills.append(skill)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to parse skill file %s — skipping.", path, exc_info=True)

    logger.info("Loaded %d skill(s) from %s", len(skills), target)
    return skills


def _iter_skill_files(directory: Path) -> Iterator[Path]:
    """Yield all *.md files under directory, excluding TEMPLATE.md."""
    for path in sorted(directory.rglob("*.md")):
        if path.name.upper() == "TEMPLATE.MD":
            continue
        yield path


def _parse_skill_file(path: Path) -> Skill | None:
    """
    Parse a single skill markdown file.

    Returns a Skill on success, None if the file should be silently skipped
    (e.g. no frontmatter — likely a README or notes file).

    Raises ValueError / KeyError for files that have frontmatter but are
    missing required fields, so the caller can log a useful warning.
    """
    if yaml is None:
        raise ImportError("PyYAML is required for skill file parsing. Run: pip install pyyaml")

    content = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(content)
    if not match:
        # No frontmatter — not a skill file, silently skip
        return None

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter in {path}: {exc}") from exc

    if not isinstance(meta, dict):
        return None

    # Required fields
    missing = [f for f in ("name", "description", "agent_name", "trigger") if not meta.get(f)]
    if missing:
        raise ValueError(
            f"Skill file {path} is missing required frontmatter field(s): {', '.join(missing)}"
        )

    # Extract procedure steps from the markdown body (lines starting with digits)
    body = content[match.end():]
    procedure = _extract_procedure(body)

    return Skill(
        skill_id=str(meta["name"]),
        agent_name=str(meta["agent_name"]),
        domain=str(meta.get("domain", _infer_domain(meta["agent_name"]))),
        trigger=str(meta["trigger"]),
        procedure=procedure,
        example_query=str(meta.get("example_query", "")),
    )


def _extract_procedure(body: str) -> list[str]:
    """Extract ordered list items from the Steps section of the markdown body."""
    steps: list[str] = []
    in_steps = False
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+Steps", stripped, re.IGNORECASE):
            in_steps = True
            continue
        if in_steps:
            if stripped.startswith("#"):
                # Next section — stop
                break
            step_match = re.match(r"^\d+\.\s+(.+)", stripped)
            if step_match:
                steps.append(step_match.group(1))
    return steps


def _infer_domain(agent_name: str) -> str:
    """Best-effort domain from agent name (e.g. 'AnalyticsAgent' -> 'analytics')."""
    return agent_name.lower().replace("agent", "").strip("-_") or "general"
