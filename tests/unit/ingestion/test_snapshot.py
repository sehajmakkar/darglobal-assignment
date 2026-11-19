import gzip
from datetime import UTC, datetime
from pathlib import Path

from dgbot.domain.models import AreaCoverage, Listing, Source
from dgbot.ingestion.snapshot import iter_snapshot, read_jsonl, write_jsonl

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _listing(lid: str) -> Listing:
    return Listing(
        id=f"wasalt:listing:{lid}",
        source=Source.WASALT,
        url=f"https://wasalt.sa/x-{lid}",
        scraped_at=NOW,
        listing_id=lid,
        purpose="sale",
        property_type="villa",
    )


def test_round_trip_sorted_and_nulls_omitted(tmp_path: Path) -> None:
    path = tmp_path / "wasalt" / "listings.jsonl"
    assert write_jsonl(path, [_listing("2"), _listing("1")]) == 2

    lines = path.read_text().splitlines()
    assert '"listing_id":"1"' in lines[0]  # sorted by id
    assert "price" not in lines[0]  # None fields omitted
    assert [r.id for r in read_jsonl(path)] == ["wasalt:listing:1", "wasalt:listing:2"]


def test_gzip_output_is_byte_for_byte_reproducible(tmp_path: Path) -> None:
    a, b = tmp_path / "a.jsonl.gz", tmp_path / "b.jsonl.gz"
    write_jsonl(a, [_listing("1")])
    write_jsonl(b, [_listing("1")])

    assert a.read_bytes() == b.read_bytes()
    assert gzip.decompress(a.read_bytes()).startswith(b"{")


def test_iter_snapshot_reads_mixed_record_types(tmp_path: Path) -> None:
    write_jsonl(tmp_path / "wasalt" / "listings.jsonl.gz", [_listing("1")])
    area = AreaCoverage(
        id="wasalt:area:sale:villas:riyadh",
        source=Source.WASALT,
        url="https://wasalt.sa/a",
        scraped_at=NOW,
        purpose="sale",
        property_type="villa",
        city="Riyadh",
    )
    write_jsonl(tmp_path / "wasalt" / "areas.jsonl", [area])

    records = list(iter_snapshot(tmp_path))
    assert {type(r).__name__ for r in records} == {"Listing", "AreaCoverage"}
