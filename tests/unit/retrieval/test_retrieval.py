"""Retriever + Qdrant (in-memory) with fake embedders: the full path, no model downloads."""

import pytest
from qdrant_client import QdrantClient

from dgbot.domain.models import Chunk, Source
from dgbot.retrieval.embeddings import prefixes_for
from dgbot.retrieval.fake import FakeDenseEmbedder, FakeSparseEmbedder
from dgbot.retrieval.retriever import HybridRetriever
from dgbot.retrieval.vectorstore import QdrantStore


def _chunk(cid: str, text: str, **meta: str) -> Chunk:
    record_id = cid.split("#")[0]
    return Chunk(
        id=cid,
        record_id=record_id,
        record_type="project",
        section="card",
        source=Source.DARGLOBAL,
        url=f"https://x/{record_id}",
        title=record_id,
        text=text,
        **meta,
    )


CHUNKS = [
    _chunk(
        "p:astera#card-0",
        "The Astera interiors by Aston Martin, Al Marjan Island, RAK",
        city="Al Marjan Island",
        country="United Arab Emirates",
    ),
    _chunk(
        "p:dg1#card-0",
        "DG1 residential tower in Business Bay, Dubai",
        city="Dubai",
        country="United Arab Emirates",
    ),
    _chunk(
        "p:pagani#card-0",
        "Da Vinci Tower with interiors by Pagani in Dubai",
        city="Dubai",
        country="United Arab Emirates",
    ),
    _chunk(
        "p:collina#card-0",
        "La Collina villas in Jeddah, Saudi Arabia",
        city="Jeddah",
        country="Saudi Arabia",
    ),
    _chunk("a:long#body-0", "Dubai golden visa guide part one Dubai Dubai"),
    _chunk("a:long#body-1", "Dubai golden visa guide part two Dubai Dubai"),
    _chunk("a:long#body-2", "Dubai golden visa guide part three Dubai Dubai"),
]


@pytest.fixture
def retriever() -> HybridRetriever:
    dense, sparse = FakeDenseEmbedder(), FakeSparseEmbedder()
    store = QdrantStore(QdrantClient(":memory:"), "test")
    store.recreate(dense.dim)
    texts = [c.text for c in CHUNKS]
    store.upsert(CHUNKS, dense.embed_documents(texts), sparse.embed_documents(texts))
    return HybridRetriever(dense, sparse, store, top_k=3)


def test_exact_name_query_ranks_the_right_project_first(retriever: HybridRetriever) -> None:
    hits = retriever.search("Pagani tower")

    assert hits[0].chunk.id == "p:pagani#card-0"
    assert hits[0].chunk.url == "https://x/p:pagani"  # payload round-trips into a Chunk


def test_filters_restrict_results(retriever: HybridRetriever) -> None:
    hits = retriever.search("villas tower residences", filters={"country": "Saudi Arabia"})

    assert [h.chunk.record_id for h in hits] == ["p:collina"]


def test_filter_with_several_values(retriever: HybridRetriever) -> None:
    hits = retriever.search("project", k=10, filters={"city": ["Jeddah", "Al Marjan Island"]})

    assert {h.chunk.record_id for h in hits} == {"p:collina", "p:astera"}


def test_at_most_two_chunks_per_record(retriever: HybridRetriever) -> None:
    hits = retriever.search("Dubai golden visa guide", k=5)

    assert sum(1 for h in hits if h.chunk.record_id == "a:long") == 2


def test_recreate_is_idempotent() -> None:
    store = QdrantStore(QdrantClient(":memory:"), "t")
    dense, sparse = FakeDenseEmbedder(), FakeSparseEmbedder()
    for _ in range(2):
        store.recreate(dense.dim)
        store.upsert(
            CHUNKS[:2], dense.embed_documents(["a", "b"]), sparse.embed_documents(["a", "b"])
        )
    assert store.count() == 2


@pytest.mark.parametrize(
    ("model", "query_prefix"),
    [
        ("intfloat/multilingual-e5-large", "query: "),
        ("google/embeddinggemma-300m", "task: search result | query: "),
        ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", ""),
    ],
)
def test_model_prefixes(model: str, query_prefix: str) -> None:
    assert prefixes_for(model)[0] == query_prefix
