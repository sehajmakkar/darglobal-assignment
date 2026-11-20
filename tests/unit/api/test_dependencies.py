import pytest
from qdrant_client import QdrantClient

from dgbot.api.dependencies import check_index
from dgbot.core.errors import SearchIndexError
from dgbot.domain.models import Chunk, Source
from dgbot.retrieval.fake import FakeDenseEmbedder, FakeSparseEmbedder
from dgbot.retrieval.vectorstore import QdrantStore


def _store(chunks: int) -> QdrantStore:
    store = QdrantStore(QdrantClient(":memory:"), "t")
    dense, sparse = FakeDenseEmbedder(), FakeSparseEmbedder()
    store.recreate(dense.dim)
    batch = [
        Chunk(
            id=f"c{n}",
            record_id=f"r{n}",
            record_type="page",
            section="body",
            source=Source.DARGLOBAL,
            title=f"t{n}",
            url=f"https://x/{n}",
            text=f"text {n}",
        )
        for n in range(chunks)
    ]
    if batch:
        texts = [c.text for c in batch]
        store.upsert(batch, dense.embed_documents(texts), sparse.embed_documents(texts))
    return store


def test_index_matching_its_manifest_passes() -> None:
    check_index(_store(3), expected_chunks=3)


@pytest.mark.parametrize(("actual", "expected"), [(0, 3102), (0, 0), (2, 3)])
def test_empty_or_partial_index_is_not_ready(actual: int, expected: int) -> None:
    """Regression (C-026): an empty Qdrant server collection reported ready: true."""
    with pytest.raises(SearchIndexError, match=f"has {actual} chunks"):
        check_index(_store(actual), expected_chunks=expected)


def test_missing_collection_is_not_ready() -> None:
    store = QdrantStore(QdrantClient(":memory:"), "never-created")
    with pytest.raises(SearchIndexError, match="unreadable"):
        check_index(store, expected_chunks=1)
