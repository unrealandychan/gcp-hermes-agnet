"""
memory/memcell_store.py

Firestore-backed storage for MemCell structured memory units.

Uses the same Firestore client pattern as the rest of the platform — no new
infrastructure required. MemCells are stored in a sub-collection scoped by user_id.

Collection layout:
    memcells/{user_id}/cells/{memcell_id}

Why Firestore (not a new vector DB)?
    - Zero new infra — already used for user profiles and session state
    - MemCell Facts are short text fragments — Firestore array-contains queries
      work well for keyword matching at this scale
    - When BM25 hybrid retrieval becomes a priority, swap to Vertex AI Search
      by implementing the same interface (upsert_memcell / fetch_memcells)

Retrieval strategy (Phase 2 — Hybrid):
    fetch_memcells() supports an optional `query` parameter. When provided:
      - BM25 via Vertex AI Search indexes MemCell Atomic Facts
      - Dense via Vertex AI RAG Engine embeds MemCell Episodes
      - Results are fused via RRF (k=60) — no manual weight tuning required
    When `query` is None, falls back to Phase 1 recency-based fetch.
    When Vertex AI services are not configured, gracefully degrades to recency.
    See: memory/memcell_retrieval.py for implementation details.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from memory.memcell_models import MemCell

logger = logging.getLogger(__name__)

_COLLECTION = "memcells"


def _get_firestore_client():
    """Lazy Firestore client — only imported when actually used."""
    try:
        from google.cloud import firestore  # type: ignore
        return firestore.AsyncClient()
    except ImportError as exc:
        raise ImportError(
            "google-cloud-firestore is required for MemCell storage. "
            "Run: pip install google-cloud-firestore"
        ) from exc


async def upsert_memcell(memcell: MemCell) -> bool:
    """
    Write (create or overwrite) a MemCell to Firestore.

    Path: memcells/{user_id}/cells/{memcell_id}

    Returns True on success, False on failure (non-blocking — caller should
    fire-and-forget this in an asyncio.create_task).
    """
    try:
        db = _get_firestore_client()
        doc_ref = (
            db.collection(_COLLECTION)
            .document(memcell.user_id)
            .collection("cells")
            .document(memcell.memcell_id)
        )
        await doc_ref.set(memcell.to_firestore_dict())
        logger.info(
            "MemCellStore: saved %s for user=%s type=%s",
            memcell.memcell_id,
            memcell.user_id,
            memcell.memory_type.value,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception(
            "MemCellStore: failed to save memcell %s for user=%s",
            memcell.memcell_id,
            memcell.user_id,
        )
        return False


async def fetch_memcells(
    user_id: str,
    limit: int = 20,
    memory_type: Optional[str] = None,
    as_of: Optional[date] = None,
    query: Optional[str] = None,
) -> list[MemCell]:
    """
    Fetch MemCells for a user.

    When ``query`` is provided, uses hybrid retrieval (BM25 + dense vector + RRF).
    When ``query`` is None, falls back to recency-based Firestore fetch.

    Args:
        user_id:     User to fetch memories for.
        limit:       Max number of cells to return (default 20).
        memory_type: Optional filter by MemoryType value string (recency mode only).
        as_of:       Date for foresight validity filtering (default: today).
        query:       Optional free-text query. When set, activates hybrid retrieval.

    Returns:
        List of MemCell objects, ranked by relevance (hybrid) or recency (fallback).
    """
    # ── Hybrid path ────────────────────────────────────────────────────────────
    if query:
        try:
            from memory.memcell_retrieval import hybrid_retrieve
            cells = await hybrid_retrieve(user_id=user_id, query=query, top_k=limit)
            if cells:
                logger.debug(
                    "MemCellStore: hybrid_retrieve returned %d cells for user=%s",
                    len(cells), user_id,
                )
                return cells
            # Both tracks returned nothing → fall through to recency fetch
            logger.debug(
                "MemCellStore: hybrid_retrieve returned 0 results — "
                "falling back to recency fetch for user=%s", user_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "MemCellStore: hybrid_retrieve failed for user=%s — "
                "falling back to recency fetch.", user_id,
            )

    # ── Recency path (original Phase 1 behaviour) ──────────────────────────────
    try:
        db = _get_firestore_client()
        fs_query = (
            db.collection(_COLLECTION)
            .document(user_id)
            .collection("cells")
            .order_by("created_at", direction="DESCENDING")
        )
        if memory_type:
            fs_query = fs_query.where("memory_type", "==", memory_type)
        fs_query = fs_query.limit(limit)

        docs = fs_query.stream()
        cells: list[MemCell] = []
        async for doc in docs:
            try:
                cells.append(MemCell.from_firestore_dict(doc.to_dict()))
            except Exception:  # noqa: BLE001
                logger.warning("MemCellStore: failed to deserialise doc %s", doc.id)

        logger.debug(
            "MemCellStore: recency fetch returned %d cells for user=%s", len(cells), user_id
        )
        return cells

    except Exception:  # noqa: BLE001
        logger.exception("MemCellStore: fetch_memcells failed for user=%s", user_id)
        return []


async def format_memcells_for_prompt(
    user_id: str,
    limit: int = 10,
    as_of: Optional[date] = None,
    max_chars: int = 3000,
    query: Optional[str] = None,
) -> str:
    """
    Fetch MemCells and format them for system prompt injection.

    When ``query`` is provided, uses hybrid retrieval so the injected memories
    are semantically relevant to the current message (EverOS adaptive injection).
    When ``query`` is None, uses recency-based fetch (original Phase 1 behaviour).

    Expired foresight is silently dropped (passive memory decay — EverOS pattern).
    Returns empty string if no memories are found.

    Args:
        user_id:   User to fetch for.
        limit:     Max cells to include.
        as_of:     Date for foresight validity (default: today).
        max_chars: Character budget cap (to avoid context window overflow).
        query:     Optional current user message for relevance ranking.

    Returns:
        Formatted string ready for system prompt injection.
    """
    cells = await fetch_memcells(user_id=user_id, limit=limit, query=query)
    if not cells:
        return ""

    lines = ["## Long-Term Memory (structured)", ""]
    used = 0

    for cell in cells:
        text = cell.to_prompt_text(as_of=as_of)
        if used + len(text) > max_chars:
            break
        lines.append(text)
        lines.append("")
        used += len(text)

    return "\n".join(lines).strip()
