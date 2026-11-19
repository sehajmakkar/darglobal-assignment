from qdrant_client import QdrantClient

from dgbot.domain.models import Chunk, Source
from dgbot.evaluation.retrieval import GoldenItem, evaluate, unknown_expected
from dgbot.retrieval.fake import FakeDenseEmbedder, FakeSparseEmbedder
from dgbot.retrieval.retriever import HybridRetriever
from dgbot.retrieval.vectorstore import QdrantStore


def _retriever(texts: dict[str, str]) -> HybridRetriever:
    chunks = [
        Chunk(
            id=f"{rid}#c-0",
            record_id=rid,
            record_type="project",
            section="card",
            source=Source.DARGLOBAL,
            url=f"https://x/{rid}",
            title=rid,
            text=text,
        )
        for rid, text in texts.items()
    ]
    dense, sparse = FakeDenseEmbedder(), FakeSparseEmbedder()
    store = QdrantStore(QdrantClient(":memory:"), "t")
    store.recreate(dense.dim)
    store.upsert(
        chunks,
        dense.embed_documents(list(texts.values())),
        sparse.embed_documents(list(texts.values())),
    )
    return HybridRetriever(dense, sparse, store)


def _item(gid: str, q: str, expected: list[str], category: str = "darglobal") -> GoldenItem:
    return GoldenItem(id=gid, question=q, lang="en", category=category, expected=expected)


def test_metrics_hit_rank_mrr_and_out_of_scope_excluded() -> None:
    r = _retriever(
        {
            "p:astera": "Astera Aston Martin beach",
            "p:dg1": "DG1 tower Business Bay",
            "wasalt:summary:city:riyadh:rent:1": "rent Riyadh districts apartments",
        }
    )
    items = [
        _item("a", "Astera Aston Martin", ["p:astera"]),
        _item("b", "apartments rent Riyadh", ["wasalt:summary:city:riyadh:rent*"], "wasalt"),
        _item("c", "weather tomorrow", [], "out_of_scope"),
    ]
    report = evaluate(r, items)

    assert report.overall.n == 2  # out-of-scope not scored
    assert report.overall.hit_at[1] == 1.0 and report.overall.mrr == 1.0
    assert set(report.by_group) == {"darglobal", "wasalt", "lang:en"}
    assert report.misses() == []


def test_unknown_expected_ids_are_reported() -> None:
    items = [_item("a", "q", ["p:astera", "p:typo", "wasalt:summary:city:riyadh:*"])]
    assert unknown_expected(items, {"p:astera", "wasalt:summary:city:riyadh:rent"}) == ["a: p:typo"]
