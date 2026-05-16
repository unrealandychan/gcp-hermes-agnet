"""Offline unit tests for memory/cross_corpus.py (Issue #10)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from memory.cross_corpus import RetrievedContext, _deduplicate, retrieve_cross_corpus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chunk(text: str, score: float) -> SimpleNamespace:
    return SimpleNamespace(text=text, score=score)


def make_rag_response(*chunks) -> SimpleNamespace:
    return SimpleNamespace(contexts=SimpleNamespace(contexts=list(chunks)))


def patched_rag(chunks_per_corpus: list[list[tuple[str, float]]]):
    """Return a context manager that patches rag.retrieval_query per call."""
    call_iter = iter(chunks_per_corpus)

    def side_effect(**kwargs):
        try:
            chunks = next(call_iter)
        except StopIteration:
            chunks = []
        return make_rag_response(*[make_chunk(t, s) for t, s in chunks])

    mock_rag = MagicMock()
    mock_rag.retrieval_query.side_effect = side_effect
    mock_rag.RagResource = lambda rag_corpus: rag_corpus
    return mock_rag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_no_corpora():
    result = await retrieve_cross_corpus("query", corpora=[])
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_single_corpus_returns_results():
    mock_rag = patched_rag([[("chunk A", 0.9), ("chunk B", 0.7)]])
    with patch("memory.cross_corpus.rag", mock_rag), patch("memory.cross_corpus._RAG_AVAILABLE", True):
        results = await retrieve_cross_corpus("test query", corpora=["corpus1"], top_k=5)
    assert len(results) == 2
    assert results[0].text == "chunk A"
    assert results[0].score == 0.9


@pytest.mark.asyncio
async def test_retrieve_merges_multiple_corpora():
    mock_rag = patched_rag(
        [[("A", 0.8)], [("B", 0.6)]],
    )
    with patch("memory.cross_corpus.rag", mock_rag), patch("memory.cross_corpus._RAG_AVAILABLE", True):
        results = await retrieve_cross_corpus("query", corpora=["c1", "c2"], top_k=10)
    texts = [r.text for r in results]
    assert "A" in texts
    assert "B" in texts


@pytest.mark.asyncio
async def test_retrieve_sorts_by_score_descending():
    mock_rag = patched_rag(
        [[("low", 0.3), ("high", 0.95)], [("mid", 0.6)]],
    )
    with patch("memory.cross_corpus.rag", mock_rag), patch("memory.cross_corpus._RAG_AVAILABLE", True):
        results = await retrieve_cross_corpus("query", corpora=["c1", "c2"], top_k=10)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_retrieve_deduplicates_identical_text():
    mock_rag = patched_rag(
        [[("same text", 0.8)], [("same text", 0.7)]],
    )
    with patch("memory.cross_corpus.rag", mock_rag), patch("memory.cross_corpus._RAG_AVAILABLE", True):
        results = await retrieve_cross_corpus("query", corpora=["c1", "c2"], top_k=10)
    texts = [r.text for r in results]
    assert texts.count("same text") == 1


@pytest.mark.asyncio
async def test_retrieve_respects_top_k():
    mock_rag = patched_rag(
        [[("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.6)]],
    )
    with patch("memory.cross_corpus.rag", mock_rag), patch("memory.cross_corpus._RAG_AVAILABLE", True):
        results = await retrieve_cross_corpus("query", corpora=["c1"], top_k=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_retrieve_falls_back_gracefully_when_rag_unavailable():
    with patch("memory.cross_corpus._RAG_AVAILABLE", False), patch("memory.cross_corpus.rag", None):
        results = await retrieve_cross_corpus("query", corpora=["corpus1", "corpus2"])
    assert results == []


def test_deduplicate_removes_duplicates():
    contexts = [
        RetrievedContext(text="hello", corpus_name="c1", score=0.9),
        RetrievedContext(text="hello", corpus_name="c2", score=0.5),
        RetrievedContext(text="world", corpus_name="c1", score=0.7),
    ]
    result = _deduplicate(contexts)
    assert len(result) == 2
    texts = [r.text for r in result]
    assert "hello" in texts
    assert "world" in texts


def test_retrieved_context_defaults():
    ctx = RetrievedContext(text="x", corpus_name="corp")
    assert ctx.score == 0.0
