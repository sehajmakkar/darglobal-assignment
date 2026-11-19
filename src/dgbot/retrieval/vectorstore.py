"""Vector store: Qdrant with a dense + BM25 sparse vector per chunk, hybrid RRF queries.

Local mode (a directory, single process) for one container; set `qdrant_url` to use a
Qdrant server for multiple replicas — same code path (D-009).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from qdrant_client import QdrantClient, models

from dgbot.domain.models import Chunk
from dgbot.retrieval.embeddings import SparseVector

DENSE = "dense"
SPARSE = "bm25"
# Payload fields we filter on → keyword indexes (only used by server mode).
FILTER_FIELDS = (
    "source",
    "record_type",
    "kind",
    "city",
    "country",
    "purpose",
    "property_type",
    "lang",
)

Filters = dict[str, str | Sequence[str]]


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    def recreate(self, dense_dim: int) -> None: ...

    def upsert(
        self, chunks: Sequence[Chunk], dense: Sequence[list[float]], sparse: Sequence[SparseVector]
    ) -> None: ...

    def search(
        self,
        dense: list[float],
        sparse: SparseVector,
        *,
        limit: int,
        prefetch: int,
        filters: Filters | None = None,
    ) -> list[SearchHit]: ...

    def count(self) -> int: ...


def open_client(index_dir: Path, url: str | None) -> QdrantClient:
    if url:
        return QdrantClient(url=url)
    (index_dir / "qdrant").mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(index_dir / "qdrant"))


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))  # stable across rebuilds


def _filter(filters: Filters | None) -> models.Filter | None:
    if not filters:
        return None
    must: list[models.Condition] = []
    for key, value in filters.items():
        match: models.MatchValue | models.MatchAny
        if isinstance(value, str):
            match = models.MatchValue(value=value)
        else:
            match = models.MatchAny(any=list(value))
        must.append(models.FieldCondition(key=key, match=match))
    return models.Filter(must=must)


class QdrantStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self._collection = collection

    def recreate(self, dense_dim: int) -> None:
        if self._client.collection_exists(self._collection):
            self._client.delete_collection(self._collection)
        self._client.create_collection(
            self._collection,
            vectors_config={
                DENSE: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
            },
            # IDF modifier: Qdrant computes BM25's inverse document frequency itself.
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    def upsert(
        self, chunks: Sequence[Chunk], dense: Sequence[list[float]], sparse: Sequence[SparseVector]
    ) -> None:
        points = [
            models.PointStruct(
                id=_point_id(chunk.id),
                vector={
                    DENSE: d,
                    SPARSE: models.SparseVector(indices=s.indices, values=s.values),
                },
                payload=chunk.model_dump(mode="json"),
            )
            for chunk, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        self._client.upsert(self._collection, points=points, wait=True)

    def search(
        self,
        dense: list[float],
        sparse: SparseVector,
        *,
        limit: int,
        prefetch: int,
        filters: Filters | None = None,
    ) -> list[SearchHit]:
        flt = _filter(filters)
        response = self._client.query_points(
            self._collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, limit=prefetch, filter=flt),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE,
                    limit=prefetch,
                    filter=flt,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [_hit(p.payload, p.score) for p in response.points if p.payload]

    def count(self) -> int:
        return self._client.count(self._collection, exact=True).count

    def record_ids(self) -> set[str]:
        """Every record id in the collection (scrolls payloads; used by evaluation)."""
        ids: set[str] = set()
        offset = None
        while True:
            points, offset = self._client.scroll(
                self._collection, limit=1000, offset=offset, with_payload=["record_id"]
            )
            ids.update(str(p.payload["record_id"]) for p in points if p.payload)
            if offset is None:
                return ids

    def close(self) -> None:
        self._client.close()


def _hit(payload: dict[str, Any], score: float) -> SearchHit:
    return SearchHit(chunk=Chunk.model_validate(payload), score=score)
