"""Snapshot → chunks → embeddings → Qdrant index (+ listings SQLite + index manifest).

Idempotent: every run rebuilds the collection from the committed snapshot, so the same
snapshot + model always gives the same index. Runs locally and in the Docker build.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from dgbot.core.errors import SearchIndexError
from dgbot.domain.models import Chunk
from dgbot.ingestion.chunking import build_chunks
from dgbot.ingestion.listings_db import build_listings_db
from dgbot.ingestion.snapshot import iter_snapshot
from dgbot.retrieval.embeddings import DenseEmbedder, SparseEmbedder
from dgbot.retrieval.vectorstore import VectorStore

logger = logging.getLogger(__name__)

INDEX_MANIFEST = "index.json"
LISTINGS_DB = "listings.sqlite"
_BATCH = 64


@dataclass(frozen=True)
class IndexReport:
    embedding_model: str
    dense_dim: int
    sparse_model: str
    chunks: int
    chunks_by_type: dict[str, int]
    listings_rows: int
    area_rows: int
    snapshot_fingerprint: str
    built_at: str
    seconds: float


def snapshot_fingerprint(root: Path) -> str:
    """sha256 over every snapshot file's path + bytes: which data an index was built from."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "QUALITY.md"):
        if path.name == "manifest.json":
            continue  # contains a generation timestamp
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def build_index(
    snapshot_dir: Path,
    index_dir: Path,
    dense: DenseEmbedder,
    sparse: SparseEmbedder,
    store: VectorStore,
    *,
    chunk_words: int,
    overlap_words: int,
) -> IndexReport:
    started = time.perf_counter()
    records = list(iter_snapshot(snapshot_dir))
    if not records:  # a wrong path or missing mount must fail, not publish an empty index
        raise SearchIndexError(f"no records in snapshot {snapshot_dir}")
    chunks = build_chunks(records, chunk_words=chunk_words, overlap_words=overlap_words)
    logger.info("%d records → %d chunks; embedding with %s", len(records), len(chunks), dense.name)

    store.recreate(dense.dim)
    for start in range(0, len(chunks), _BATCH):
        batch: list[Chunk] = chunks[start : start + _BATCH]
        texts = [c.text for c in batch]
        store.upsert(batch, dense.embed_documents(texts), sparse.embed_documents(texts))
        if (start // _BATCH) % 10 == 0:
            logger.info("indexed %d / %d chunks", min(start + _BATCH, len(chunks)), len(chunks))

    listings, areas = build_listings_db(index_dir / LISTINGS_DB, records)
    by_type: dict[str, int] = {}
    for chunk in chunks:
        by_type[chunk.record_type] = by_type.get(chunk.record_type, 0) + 1

    report = IndexReport(
        embedding_model=dense.name,
        dense_dim=dense.dim,
        sparse_model=sparse.name,
        chunks=store.count(),
        chunks_by_type=dict(sorted(by_type.items())),
        listings_rows=listings,
        area_rows=areas,
        snapshot_fingerprint=snapshot_fingerprint(snapshot_dir),
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        seconds=round(time.perf_counter() - started, 1),
    )
    (index_dir / INDEX_MANIFEST).write_text(json.dumps(asdict(report), indent=2) + "\n")
    return report
