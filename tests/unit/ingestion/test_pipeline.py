import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import QdrantClient

from dgbot.domain.models import AreaCoverage, Faq, Listing, Project, Source
from dgbot.ingestion.pipeline import build_index
from dgbot.ingestion.snapshot import write_jsonl
from dgbot.retrieval.fake import FakeDenseEmbedder, FakeSparseEmbedder
from dgbot.retrieval.vectorstore import QdrantStore

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _snapshot(root: Path) -> None:
    project = Project(
        id="darglobal:project:dg1",
        source=Source.DARGLOBAL,
        url="https://darglobal.co.uk/dg1",
        scraped_at=NOW,
        name="DG1",
        location="Dubai, UAE",
        country="United Arab Emirates",
        description="A tower in Business Bay.",
        faqs=[Faq(question="Where is DG1?", answer="Business Bay.")],
    )
    listing = Listing(
        id="wasalt:listing:1",
        source=Source.WASALT,
        url="https://wasalt.sa/en/property/sale/villa-1",
        scraped_at=NOW,
        listing_id="1",
        purpose="sale",
        property_type="villa",
        bedrooms=4,
    )
    area = AreaCoverage(
        id="wasalt:area:sale:villas:riyadh",
        source=Source.WASALT,
        url="https://wasalt.sa/en/v",
        scraped_at=NOW,
        purpose="sale",
        property_type="villa",
        city="Riyadh",
    )
    write_jsonl(root / "darglobal" / "projects.jsonl", [project])
    write_jsonl(root / "wasalt" / "listings.jsonl.gz", [listing])
    write_jsonl(root / "wasalt" / "areas.jsonl.gz", [area])


def test_build_index_end_to_end(tmp_path: Path) -> None:
    snap, index = tmp_path / "processed", tmp_path / "index"
    _snapshot(snap)
    store = QdrantStore(QdrantClient(":memory:"), "t")

    report = build_index(
        snap,
        index,
        FakeDenseEmbedder(),
        FakeSparseEmbedder(),
        store,
        chunk_words=200,
        overlap_words=40,
    )

    # project: card + details + 1 FAQ; Wasalt: overview + city summary (type stats need ≥20)
    assert report.chunks == store.count() == 5
    assert report.chunks_by_type == {"project": 3, "summary": 2}
    assert (report.listings_rows, report.area_rows) == (1, 1)
    manifest = json.loads((index / "index.json").read_text())
    assert (
        manifest["embedding_model"] == "fake-dense" and len(manifest["snapshot_fingerprint"]) == 16
    )

    with sqlite3.connect(index / "listings.sqlite") as db:
        assert db.execute("SELECT purpose, property_type, bedrooms FROM listings").fetchall() == [
            ("sale", "villa", 4)
        ]
        assert db.execute("SELECT city FROM areas").fetchall() == [("Riyadh",)]


def test_rebuild_gives_same_fingerprint(tmp_path: Path) -> None:
    snap = tmp_path / "processed"
    _snapshot(snap)
    reports = [
        build_index(
            snap,
            tmp_path / f"i{n}",
            FakeDenseEmbedder(),
            FakeSparseEmbedder(),
            QdrantStore(QdrantClient(":memory:"), "t"),
            chunk_words=200,
            overlap_words=40,
        )
        for n in range(2)
    ]
    assert reports[0].snapshot_fingerprint == reports[1].snapshot_fingerprint
