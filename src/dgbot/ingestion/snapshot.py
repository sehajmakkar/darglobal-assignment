"""The processed data snapshot: JSONL files under `data/processed/` (D-006, D-033).

This module is the single definition of the on-disk format. The offline scraper writes
it; ingestion (Docker build time) reads it — so it must not import scraping code.

Layout:
    data/processed/
      manifest.json                 counts, generation time, source fetch window
      darglobal/{projects,partners,articles,pages}.jsonl
      wasalt/listings.jsonl.gz      ~63k slug-derived listings (gzipped: large)
      wasalt/areas.jsonl.gz         city/district/type coverage
      wasalt/sample_listings.jsonl  the hand-saved, price-bearing listings (readable)
"""

from __future__ import annotations

import gzip
import io
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from dgbot.domain.models import AnyRecord

_ADAPTER: TypeAdapter[AnyRecord] = TypeAdapter(AnyRecord)
SCHEMA_VERSION = 1


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    """Write records sorted by id, one JSON object per line, nulls omitted.

    `.gz` paths are gzipped with mtime=0 so identical data gives identical bytes
    (clean git diffs, reproducible Docker layers).
    """
    rows = sorted(records, key=lambda r: str(getattr(r, "id", "")))
    payload = "".join(r.model_dump_json(exclude_none=True) + "\n" for r in rows).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as gz:
            gz.write(payload)
        path.write_bytes(buffer.getvalue())
    else:
        path.write_bytes(payload)
    return len(rows)


def read_jsonl(path: Path) -> Iterator[AnyRecord]:
    """Validated records from one snapshot file (plain or gzipped)."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield _ADAPTER.validate_json(line)


def iter_snapshot(root: Path) -> Iterator[AnyRecord]:
    """Every record in the snapshot, file by file in a stable order."""
    for path in sorted(root.rglob("*.jsonl")) + sorted(root.rglob("*.jsonl.gz")):
        yield from read_jsonl(path)


def write_manifest(
    root: Path, counts: dict[str, int], fetch_window: tuple[datetime, datetime]
) -> None:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_fetched": {
            "from": fetch_window[0].isoformat(timespec="seconds"),
            "to": fetch_window[1].isoformat(timespec="seconds"),
        },
        "files": dict(sorted(counts.items())),
        "total_records": sum(counts.values()),
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
