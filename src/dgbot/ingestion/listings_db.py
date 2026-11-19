"""Wasalt listings + area coverage → SQLite, for exact filters/counts (D-018).

Vector search is bad at "how many 3-bedroom villas for sale" — SQL is exact. The Phase 4
`search_listings` tool queries this file. Built next to the vector index from the snapshot.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from dgbot.domain.models import AnyRecord, AreaCoverage, Listing

_LISTING_COLUMNS = (
    "id",
    "listing_id",
    "lang",
    "detail",
    "purpose",
    "property_type",
    "furnishing",
    "area_sqm",
    "area_inferred",
    "bedrooms",
    "bathrooms",
    "facing",
    "street_width_m",
    "price",
    "currency",
    "price_period",
    "city",
    "zone",
    "district",
    "latitude",
    "longitude",
    "title",
    "url",
    "url_ar",
    "listed_at",
)
_AREA_COLUMNS = ("id", "purpose", "property_type", "city", "zone", "district", "url")


def _columns(names: tuple[str, ...]) -> str:
    return ", ".join(f"{c} TEXT PRIMARY KEY" if c == "id" else c for c in names)


_SCHEMA = f"""
CREATE TABLE listings ({_columns(_LISTING_COLUMNS)});
CREATE TABLE areas ({_columns(_AREA_COLUMNS)});
CREATE INDEX listings_filter ON listings (purpose, property_type, bedrooms);
CREATE INDEX listings_city ON listings (city, district);
CREATE INDEX areas_city ON areas (city, purpose, property_type);
"""


def build_listings_db(path: Path, records: Iterable[AnyRecord]) -> tuple[int, int]:
    """(Re)create the database. Returns (listings, areas) row counts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    listings: dict[str, tuple[object, ...]] = {}
    areas: dict[str, tuple[object, ...]] = {}
    for record in records:
        if isinstance(record, Listing):
            row = record.model_dump(mode="json")
            listings[record.id] = tuple(row.get(c) for c in _LISTING_COLUMNS)
        elif isinstance(record, AreaCoverage):
            row = record.model_dump(mode="json")
            areas[record.id] = tuple(row.get(c) for c in _AREA_COLUMNS)
    with sqlite3.connect(tmp) as db:
        db.executescript(_SCHEMA)
        db.executemany(
            f"INSERT INTO listings VALUES ({', '.join('?' * len(_LISTING_COLUMNS))})",
            listings.values(),
        )
        db.executemany(
            f"INSERT INTO areas VALUES ({', '.join('?' * len(_AREA_COLUMNS))})", areas.values()
        )
    tmp.replace(path)  # atomic: readers never see a half-built file
    return len(listings), len(areas)
