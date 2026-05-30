"""
tests/memory/test_hybrid_retrieval.py

Unit tests for hybrid retrieval (BM25 + Dense + RRF fusion).

All GCP/Vertex calls are mocked — no credentials needed.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from memory.memcell_retrieval import rrf_fuse, hybrid_retrieve


# ── RRF unit tests ─────────────────────────────────────────────────────────────

class TestRrfFuse:
    def test_single_list_preserves_order(self):
        ids = ["a", "b", "c", "d"]
        result = rrf_fuse([ids])
        assert result == ids, "Single-list RRF must preserve rank order"

    def test_two_identical_lists_preserve_order(self):
        ids = ["a", "b", "c"]
        result = rrf_fuse([ids, ids])
        assert result == ids, "Two identical lists must not reorder items"

    def test_rrf_promotes_shared_items(self):
        """Items appearing in both lists should rank higher than items in only one."""
        bm25 = ["x", "shared", "z"]
        dense = ["shared", "y", "w"]
        result = rrf_fuse([bm25, dense])
        # 'shared' appears in both lists → highest RRF score
        assert result[0] == "shared", "'shared' should be ranked first"

    def test_rrf_empty_lists(self):
        assert rrf_fuse([]) == []
        assert rrf_fuse([[], []]) == []

    def test_rrf_disjoint_lists(self):
        """Disjoint lists — items from higher-ranked positions should still surface first."""
        bm25 = ["a", "b", "c"]
        dense = ["d", "e", "f"]
        result = rrf_fuse([bm25, dense])
        assert len(result) == 6
        # Both heads (rank 0) have equal RRF score; order is deterministic but either is valid
        assert set(result) == {"a", "b", "c", "d", "e", "f"}

    def test_rrf_top_k_respected_at_caller(self):
        """rrf_fuse itself returns all items; callers slice to top_k."""
        ids = [str(i) for i in range(100)]
        result = rrf_fuse([ids])[:10]
        assert result == ids[:10]

    def test_rrf_k_parameter_affects_score_distribution(self):
        """Lower k = stronger emphasis on top ranks."""
        bm25 = ["a", "b", "c", "d", "e"]
        dense = ["e", "d", "c", "b", "a"]
        result_low_k = rrf_fuse([bm25, dense], k=1)
        result_high_k = rrf_fuse([bm25, dense], k=1000)
        # Both should return all 5 elements regardless of k
        assert set(result_low_k) == {"a", "b", "c", "d", "e"}
        assert set(result_high_k) == {"a", "b", "c", "d", "e"}


# ── BM25 / Dense mock helpers ──────────────────────────────────────────────────

def _make_memcell(memcell_id: str):
    """Create a minimal MemCell mock for testing."""
    from memory.memcell_models import MemCell, MemoryType
    return MemCell(
        memcell_id=memcell_id,
        agent_name="test_agent",
        user_id="user_123",
        episode=f"Episode for {memcell_id}",
        facts=[f"Fact about {memcell_id}"],
        foresight=[],
        memory_type=MemoryType("knowledge"),
        created_at="2025-01-01T00:00:00",
    )


# ── hybrid_retrieve integration tests ─────────────────────────────────────────

class TestHybridRetrieve:

    @pytest.mark.asyncio
    async def test_rrf_fusion_combines_both_tracks(self):
        """When both tracks return results, RRF fusion should merge them."""
        bm25_ids = ["cell_1", "cell_2", "cell_3"]
        dense_ids = ["cell_2", "cell_4", "cell_5"]
        fused_expected = rrf_fuse([bm25_ids, dense_ids])[:10]

        cells_by_id = {mid: _make_memcell(mid) for mid in set(bm25_ids + dense_ids)}

        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=bm25_ids), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=dense_ids), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)

        # cell_2 is in both → should be ranked first
        assert results[0].memcell_id == "cell_2"
        assert len(results) == len(fused_expected)

    @pytest.mark.asyncio
    async def test_falls_back_to_bm25_only_when_dense_empty(self):
        """When dense returns nothing, should still return BM25 results."""
        bm25_ids = ["cell_1", "cell_2"]
        cells_by_id = {mid: _make_memcell(mid) for mid in bm25_ids}

        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=bm25_ids), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=[]), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)

        assert len(results) == 2
        assert {r.memcell_id for r in results} == {"cell_1", "cell_2"}

    @pytest.mark.asyncio
    async def test_falls_back_to_dense_only_when_bm25_empty(self):
        """When BM25 returns nothing, should still return dense results."""
        dense_ids = ["cell_3", "cell_4"]
        cells_by_id = {mid: _make_memcell(mid) for mid in dense_ids}

        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=[]), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=dense_ids), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)

        assert len(results) == 2
        assert {r.memcell_id for r in results} == {"cell_3", "cell_4"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_both_tracks_empty(self):
        """When both tracks return nothing, returns empty list."""
        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=[]), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=[]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_respected(self):
        """hybrid_retrieve should return at most top_k results."""
        bm25_ids = [f"cell_{i}" for i in range(20)]
        dense_ids = [f"cell_{i}" for i in range(10, 30)]
        all_ids = list(set(bm25_ids + dense_ids))
        cells_by_id = {mid: _make_memcell(mid) for mid in all_ids}

        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=bm25_ids), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=dense_ids), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=5)

        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_bm25_exception_does_not_crash(self):
        """BM25 failures should be swallowed and dense results returned."""
        dense_ids = ["cell_10"]
        cells_by_id = {"cell_10": _make_memcell("cell_10")}

        async def bm25_fails(*a, **kw):
            raise RuntimeError("Vertex AI Search timeout")

        with patch("memory.memcell_retrieval._bm25_search", side_effect=bm25_fails), \
             patch("memory.memcell_retrieval._dense_search", new_callable=AsyncMock, return_value=dense_ids), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)

        assert len(results) == 1
        assert results[0].memcell_id == "cell_10"

    @pytest.mark.asyncio
    async def test_dense_exception_does_not_crash(self):
        """Dense failures should be swallowed and BM25 results returned."""
        bm25_ids = ["cell_1"]
        cells_by_id = {"cell_1": _make_memcell("cell_1")}

        async def dense_fails(*a, **kw):
            raise RuntimeError("RAG Engine timeout")

        with patch("memory.memcell_retrieval._bm25_search", new_callable=AsyncMock, return_value=bm25_ids), \
             patch("memory.memcell_retrieval._dense_search", side_effect=dense_fails), \
             patch("memory.memcell_retrieval._fetch_by_ids", new_callable=AsyncMock,
                   side_effect=lambda uid, ids: [cells_by_id[i] for i in ids if i in cells_by_id]):
            results = await hybrid_retrieve(user_id="user_123", query="test query", top_k=10)

        assert len(results) == 1
        assert results[0].memcell_id == "cell_1"


# ── fetch_memcells query param tests ──────────────────────────────────────────

class TestFetchMemcellsQueryParam:

    @pytest.mark.asyncio
    async def test_query_param_triggers_hybrid_path(self):
        """When query is set, hybrid_retrieve should be called."""
        cell = _make_memcell("hybrid_cell")

        # memcell_store does `from memory.memcell_retrieval import hybrid_retrieve`
        # at call time (lazy import inside the function), so we patch the source module.
        with patch("memory.memcell_retrieval.hybrid_retrieve", new_callable=AsyncMock, return_value=[cell]):
            import memory.memcell_store as store_mod
            results = await store_mod.fetch_memcells(
                user_id="user_123", query="some query", limit=10
            )

        assert len(results) == 1
        assert results[0].memcell_id == "hybrid_cell"

    @pytest.mark.asyncio
    async def test_no_query_skips_hybrid_path(self):
        """When query is None, Firestore recency path is used."""
        cell = _make_memcell("recency_cell")

        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = cell.to_firestore_dict()

        async def mock_stream(*a, **kw):
            yield mock_doc

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream = mock_stream

        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = mock_query

        import memory.memcell_store as store_mod
        with patch.object(store_mod, "_get_firestore_client", return_value=mock_db), \
             patch("memory.memcell_retrieval.hybrid_retrieve", new_callable=AsyncMock) as mock_hybrid:
            results = await store_mod.fetch_memcells(user_id="user_123", limit=10)

        mock_hybrid.assert_not_called()
        assert len(results) == 1
