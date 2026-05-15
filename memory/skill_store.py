"""
memory/skill_store.py

Manages persistence of skills in the Vertex AI RAG skills corpus.

- upsert_skill: add a new skill or version an existing one (marks old as is_current=False).
- search_skills: retrieve top-k current skills matching a query.

Scale notes:
- search_skills uses rag.retrieval_query (non-blocking async-compatible).
- _upload_skill wraps the blocking rag.upload_file in asyncio.to_thread so it
  never stalls the event loop under high concurrency.
"""
from __future__ import annotations

import logging

from vertexai.preview import rag

from config import get_settings
from memory.skill_models import Skill

logger = logging.getLogger(__name__)

_VERSION_THRESHOLD = 0.85  # similarity above this → new version of existing skill
_MAX_RESULTS = 5


def _get_corpus_name() -> str:
    name = get_settings().skills_corpus_name
    if not name:
        raise ValueError("SKILLS_CORPUS_NAME is not configured.")
    return name


def search_skills(query: str, top_k: int = _MAX_RESULTS) -> list[Skill]:
    """
    Retrieve the top-k current skills from the skills corpus matching `query`.
    Skips entries that fail to parse (corpus may contain non-skill documents).
    """
    corpus_name = _get_corpus_name()
    try:
        response = rag.retrieval_query(
            rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
            text=query,
            similarity_top_k=top_k * 2,  # oversample, then filter is_current
            vector_distance_threshold=0.4,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Skills corpus retrieval failed.")
        return []

    skills: list[Skill] = []
    for ctx in response.contexts.contexts:
        if len(skills) >= top_k:
            break
        metadata = ctx.metadata or {}
        if metadata.get("is_current", "True") != "True":
            continue
        # Reconstruct a minimal Skill for display; full JSON not stored in plain text
        # We only need trigger + procedure for prompt injection.
        text = ctx.text or ""
        # Parse from stored RAG text (to_rag_text format)
        try:
            skill = _parse_rag_text(text)
            if skill:
                skills.append(skill)
        except Exception:  # noqa: BLE001
            pass
    return skills


def _parse_rag_text(text: str) -> Skill | None:
    """Parse a Skill back from its to_rag_text() representation."""
    lines = text.splitlines()
    data: dict = {}
    procedure: list[str] = []
    in_procedure = False

    for line in lines:
        if line.startswith("SKILL:"):
            parts = line.removeprefix("SKILL:").strip().split(" (v")
            data["skill_id"] = parts[0].strip()
            data["version"] = int(parts[1].rstrip(")")) if len(parts) > 1 else 1
        elif line.startswith("AGENT:"):
            data["agent_name"] = line.removeprefix("AGENT:").strip()
        elif line.startswith("DOMAIN:"):
            data["domain"] = line.removeprefix("DOMAIN:").strip()
        elif line.startswith("TRIGGER:"):
            data["trigger"] = line.removeprefix("TRIGGER:").strip()
            in_procedure = False
        elif line.startswith("EXAMPLE:"):
            data["example_query"] = line.removeprefix("EXAMPLE:").strip()
            in_procedure = False
        elif line.startswith("PROCEDURE:"):
            in_procedure = True
        elif line.startswith("IS_CURRENT:"):
            data["is_current"] = line.removeprefix("IS_CURRENT:").strip() == "True"
            in_procedure = False
        elif line.startswith("CREATED:"):
            data["created_at"] = line.removeprefix("CREATED:").strip()
            in_procedure = False
        elif in_procedure and line.strip():
            # Strip leading "  N. "
            step = line.strip()
            step = step.lstrip("0123456789. ")
            procedure.append(step)

    if not data.get("skill_id") or not data.get("agent_name"):
        return None
    data["procedure"] = procedure
    return Skill(**data)


async def upsert_skill(new_skill: Skill) -> None:
    """
    Insert a new skill or create a new version if a near-duplicate exists.

    Near-duplicate detection: search for the skill's trigger text; if a result
    with the same skill_id and score >= VERSION_THRESHOLD exists, archive it first.
    """
    corpus_name = _get_corpus_name()
    existing = search_skills(new_skill.trigger, top_k=3)

    for ex in existing:
        if ex.skill_id == new_skill.skill_id:
            # Archive the old version — update its is_current flag by re-uploading
            archived = ex.model_copy(update={"is_current": False})
            await _upload_skill(corpus_name, archived)
            new_skill = new_skill.model_copy(update={"version": ex.version + 1})
            logger.info(
                "Versioned skill %s: v%d -> v%d",
                new_skill.skill_id,
                ex.version,
                new_skill.version,
            )
            break

    await _upload_skill(corpus_name, new_skill)
    logger.info("Persisted skill %s v%d to corpus.", new_skill.skill_id, new_skill.version)


async def _upload_skill(corpus_name: str, skill: Skill) -> None:
    """Upload skill as a RagFile text blob.

    rag.upload_file is a blocking SDK call — wrapping it in asyncio.to_thread
    prevents it from stalling the event loop under high concurrency.
    """
    import asyncio
    import tempfile
    from pathlib import Path

    def _blocking_upload() -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            prefix=f"{skill.skill_id}_v{skill.version}_",
        ) as tmp:
            tmp.write(skill.to_rag_text())
            tmp_path = Path(tmp.name)

        try:
            rag.upload_file(
                corpus_name=corpus_name,
                path=str(tmp_path),
                display_name=f"{skill.skill_id}_v{skill.version}",
                description=skill.trigger,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    await asyncio.to_thread(_blocking_upload)
