"""Cross-Corpus RAG retrieval (Issue #10)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    from vertexai import rag  # type: ignore
    _RAG_AVAILABLE = True
except Exception:  # noqa: BLE001
    rag = None  # type: ignore
    _RAG_AVAILABLE = False


@dataclass
class RetrievedContext:
    text: str
    corpus_name: str
    score: float = 0.0


def _query_corpus(corpus: Any, query: str, top_k: int) -> list[RetrievedContext]:
    """Query a single corpus. Returns empty list on failure."""
    if not _RAG_AVAILABLE or rag is None:
        logger.warning("vertexai.rag not available; skipping corpus %s", corpus)
        return []
    try:
        response = rag.retrieval_query(
            rag_resources=[rag.RagResource(rag_corpus=corpus)],
            text=query,
            similarity_top_k=top_k,
        )
        results: list[RetrievedContext] = []
        for chunk in response.contexts.contexts:
            results.append(
                RetrievedContext(
                    text=chunk.text,
                    corpus_name=str(corpus),
                    score=getattr(chunk, "score", 0.0),
                )
            )
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to query corpus %s: %s", corpus, exc)
        return []


def _deduplicate(contexts: list[RetrievedContext]) -> list[RetrievedContext]:
    seen: set[str] = set()
    unique: list[RetrievedContext] = []
    for ctx in contexts:
        key = ctx.text.strip()
        if key not in seen:
            seen.add(key)
            unique.append(ctx)
    return unique


def retrieve_cross_corpus(
    query: str,
    corpora: list[Any],
    top_k: int = 5,
) -> list[RetrievedContext]:
    """Query multiple corpora, merge results, sort by score, and deduplicate.

    Args:
        query: The search query string.
        corpora: List of corpus resource names or RagCorpus objects.
        top_k: Maximum number of results to return after merging.

    Returns:
        A sorted, deduplicated list of RetrievedContext (up to top_k).
    """
    if not corpora:
        return []

    all_results: list[RetrievedContext] = []
    for corpus in corpora:
        all_results.extend(_query_corpus(corpus, query, top_k))

    # Sort descending by score
    all_results.sort(key=lambda c: c.score, reverse=True)

    # Deduplicate
    all_results = _deduplicate(all_results)

    return all_results[:top_k]
