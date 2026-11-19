"""HybridRetriever: question → the most relevant chunks (dense + BM25, RRF, diversified)."""

from __future__ import annotations

from collections import Counter

from dgbot.retrieval.embeddings import DenseEmbedder, SparseEmbedder
from dgbot.retrieval.vectorstore import Filters, SearchHit, VectorStore


class HybridRetriever:
    """Embeds the query both ways, asks the store for a fused ranking, then keeps at most
    `max_per_record` chunks per record so one long article can't take every slot."""

    def __init__(
        self,
        dense: DenseEmbedder,
        sparse: SparseEmbedder,
        store: VectorStore,
        *,
        top_k: int = 8,
        prefetch_k: int = 40,
        max_per_record: int = 2,
    ) -> None:
        self._dense = dense
        self._sparse = sparse
        self._store = store
        self.top_k = top_k
        self._prefetch_k = prefetch_k
        self._max_per_record = max_per_record

    def search(
        self, query: str, *, k: int | None = None, filters: Filters | None = None
    ) -> list[SearchHit]:
        limit = k or self.top_k
        hits = self._store.search(
            self._dense.embed_query(query),
            self._sparse.embed_query(query),
            limit=limit * 3,  # over-fetch, then diversify
            prefetch=max(self._prefetch_k, limit * 3),
            filters=filters,
        )
        per_record: Counter[str] = Counter()
        kept: list[SearchHit] = []
        for hit in hits:
            if per_record[hit.chunk.record_id] >= self._max_per_record:
                continue
            per_record[hit.chunk.record_id] += 1
            kept.append(hit)
            if len(kept) == limit:
                break
        return kept
