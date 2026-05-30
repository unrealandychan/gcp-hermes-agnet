"""
memory/memcell_retrieval.py

EverOS-inspired Hybrid Retrieval for MemCells.

Two retrieval tracks fused via Reciprocal Rank Fusion (RRF):
  Track 1 — BM25 (Vertex AI Search)
             Indexes each MemCell's Atomic Facts (short, keyword-rich).
             Best for: exact terms, names, policy references, tool names.

  Track 2 — Dense Vector (Vertex AI RAG Engine)
             Embeds each MemCell's Episode (narrative summary).
             Best for: paraphrases, conceptual matches, semantic similarity.

  Fusion  — RRF(k=60) combines both ranked lists without manual weight tuning.
             EverOS paper shows this beats single-track retrieval by up to +19.7%
             on multi-hop memory questions (arXiv:2601.02163).

GCP-native stack — no Elasticsearch, no Pinecone, no new infra:
  BM25   → Vertex AI Search (Discovery Engine)
  Dense  → Vertex AI RAG Engine (already used for skills corpus)
  Store  → Firestore (already used for user profiles)

Graceful degradation:
  - If Vertex AI Search is not configured → falls back to dense-only
  - If RAG Engine is not configured → falls back to BM25-only
  - If neither is configured → falls back to recency-based fetch from Firestore

Environment variables (all optional, graceful degradation if absent):
  MEMCELL_SEARCH_ENGINE_ID   — Vertex AI Search data store ID for MemCell facts
  MEMCELL_SERVING_CONFIG     — Serving config name (default: default_config)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── RRF Implementation ─────────────────────────────────────────────────────────

def rrf_fuse(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[str]:
    """
    Reciprocal Rank Fusion over multiple ranked ID lists.

    For each document ID, its RRF score is the sum of 1/(k + rank) across all
    lists it appears in (1-indexed). Higher score = more relevant.

    Args:
        ranked_lists: List of ranked document ID lists (each from one retrieval track).
        k:            RRF constant — controls the importance of rank position.
                      k=60 is the standard value from Cormack et al. 2009.

    Returns:
        Merged list of document IDs, sorted by descending RRF score.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


# ── BM25 Track — Vertex AI Search ─────────────────────────────────────────────

async def _bm25_search(
    user_id: str,
    query: str,
    top_k: int = 40,
) -> list[str]:
    """
    BM25 search over MemCell Atomic Facts via Vertex AI Search.

    Returns a ranked list of memcell_ids. Falls back to [] if the
    search engine is not configured or the call fails.

    Vertex AI Search data store layout:
        Each MemCell is indexed as a document with:
          id:      memcell_id
          content: joined Atomic Facts (one per line)
          user_id: for scoping (filtered in query)
    """
    try:
        from config import get_settings
        settings = get_settings()
        engine_id = getattr(settings, "memcell_search_engine_id", None)
        if not engine_id:
            logger.debug("BM25: MEMCELL_SEARCH_ENGINE_ID not set — skipping BM25 track.")
            return []

        serving_config = getattr(settings, "memcell_serving_config", "default_config")
        project = settings.gcp_project_id
        location = settings.gcp_location

        def _blocking() -> list[str]:
            from google.cloud import discoveryengine_v1  # type: ignore

            client = discoveryengine_v1.SearchServiceClient()
            serving_config_path = (
                f"projects/{project}/locations/{location}"
                f"/collections/default_collection/engines/{engine_id}"
                f"/servingConfigs/{serving_config}"
            )
            # Filter to only this user's MemCells
            request = discoveryengine_v1.SearchRequest(
                serving_config=serving_config_path,
                query=query,
                page_size=top_k,
                filter=f'user_id: ANY("{user_id}")',
                query_expansion_spec=discoveryengine_v1.SearchRequest.QueryExpansionSpec(
                    condition=discoveryengine_v1.SearchRequest.QueryExpansionSpec.Condition.AUTO,
                ),
            )
            response = client.search(request=request)
            return [r.document.id for r in response.results if r.document.id]

        ids = await asyncio.to_thread(_blocking)
        logger.debug("BM25: returned %d results for query=%r user=%s", len(ids), query[:60], user_id)
        return ids

    except ImportError:
        logger.debug("BM25: google-cloud-discoveryengine not installed — skipping BM25 track.")
        return []
    except Exception:  # noqa: BLE001
        logger.exception("BM25: search failed for user=%s query=%r — continuing without BM25.", user_id, query[:60])
        return []


# ── Dense Track — Vertex AI RAG Engine ────────────────────────────────────────

async def _dense_search(
    user_id: str,
    query: str,
    top_k: int = 40,
) -> list[str]:
    """
    Dense vector search over MemCell Episodes via Vertex AI RAG.

    Returns a ranked list of memcell_ids. Falls back to [] if the
    RAG corpus is not configured or the call fails.

    The RAG corpus is seeded by memcell_store.index_memcell_for_rag()
    (called from upsert_memcell when MEMCELL_RAG_CORPUS_NAME is set).
    Each RAG document has metadata: {memcell_id: "...", user_id: "..."}
    """
    try:
        from config import get_settings
        settings = get_settings()
        corpus_name = getattr(settings, "memcell_rag_corpus_name", None)
        if not corpus_name:
            logger.debug("Dense: MEMCELL_RAG_CORPUS_NAME not set — skipping dense track.")
            return []

        def _blocking() -> list[str]:
            from vertexai.preview import rag  # type: ignore

            response = rag.retrieval_query(
                rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
                text=query,
                similarity_top_k=top_k,
                # Filter by user_id via metadata if supported by corpus type
            )
            ids = []
            for context in (response.contexts.contexts if response.contexts else []):
                # Extract memcell_id from source_display_name or metadata
                meta = getattr(context, "source_metadata", {}) or {}
                memcell_id = meta.get("memcell_id") or getattr(context, "source_display_name", None)
                # Only include results belonging to this user
                if meta.get("user_id", user_id) == user_id and memcell_id:
                    ids.append(memcell_id)
            return ids

        ids = await asyncio.to_thread(_blocking)
        logger.debug("Dense: returned %d results for query=%r user=%s", len(ids), query[:60], user_id)
        return ids

    except ImportError:
        logger.debug("Dense: vertexai.preview.rag not available — skipping dense track.")
        return []
    except Exception:  # noqa: BLE001
        logger.exception("Dense: RAG search failed for user=%s — continuing without dense track.", user_id)
        return []


# ── Fetch by IDs from Firestore ────────────────────────────────────────────────

async def _fetch_by_ids(user_id: str, memcell_ids: list[str]) -> list:
    """
    Fetch MemCell objects from Firestore by their IDs, preserving rank order.
    Missing IDs are silently skipped.
    """
    if not memcell_ids:
        return []

    try:
        from google.cloud import firestore  # type: ignore
        from memory.memcell_models import MemCell

        db = firestore.AsyncClient()
        tasks = [
            db.collection("memcells").document(user_id).collection("cells").document(mid).get()
            for mid in memcell_ids
        ]
        docs = await asyncio.gather(*tasks, return_exceptions=True)

        cells = []
        for mid, doc in zip(memcell_ids, docs):
            if isinstance(doc, Exception):
                logger.warning("Failed to fetch memcell %s: %s", mid, doc)
                continue
            if doc.exists:
                try:
                    cells.append(MemCell.from_firestore_dict(doc.to_dict()))
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to deserialise memcell %s", mid)
        return cells

    except Exception:  # noqa: BLE001
        logger.exception("_fetch_by_ids failed for user=%s", user_id)
        return []


# ── Public API ─────────────────────────────────────────────────────────────────

async def hybrid_retrieve(
    user_id: str,
    query: str,
    top_k: int = 10,
    rrf_k: int = 60,
) -> list:
    """
    Hybrid retrieval: BM25 + Dense vector, fused via RRF.

    Falls back gracefully:
      - Both tracks available → RRF fusion (best quality)
      - Only one track available → single-track results
      - Neither available → empty list (caller falls back to recency fetch)

    Args:
        user_id: User whose MemCells to search.
        query:   The search query (typically the user's current message).
        top_k:   Number of MemCells to return after fusion.
        rrf_k:   RRF constant (default 60 per Cormack et al. 2009).

    Returns:
        List of MemCell objects ranked by hybrid relevance score.
    """
    # Run both tracks concurrently; capture exceptions so one failure doesn't kill both
    results = await asyncio.gather(
        _bm25_search(user_id, query, top_k=top_k * 3),
        _dense_search(user_id, query, top_k=top_k * 3),
        return_exceptions=True,
    )

    bm25_ids: list[str] = []
    dense_ids: list[str] = []

    for track_name, result in zip(("BM25", "Dense"), results):
        if isinstance(result, BaseException):
            logger.exception(
                "hybrid_retrieve: %s track raised %s — continuing without it.",
                track_name, type(result).__name__,
                exc_info=result,
            )
        else:
            if track_name == "BM25":
                bm25_ids = result
            else:
                dense_ids = result

    ranked_lists = [lst for lst in [bm25_ids, dense_ids] if lst]

    if not ranked_lists:
        logger.debug("hybrid_retrieve: no tracks available for user=%s", user_id)
        return []

    fused_ids = rrf_fuse(ranked_lists, k=rrf_k)[:top_k]
    cells = await _fetch_by_ids(user_id, fused_ids)

    logger.info(
        "hybrid_retrieve: user=%s query=%r bm25=%d dense=%d fused=%d returned=%d",
        user_id, query[:60], len(bm25_ids), len(dense_ids), len(fused_ids), len(cells),
    )
    return cells
