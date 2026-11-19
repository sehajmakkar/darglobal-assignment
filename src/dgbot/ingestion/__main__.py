"""Build the search index from the committed snapshot.

    uv run python -m dgbot.ingestion                       # model from Settings
    uv run python -m dgbot.ingestion --model intfloat/multilingual-e5-large \\
        --index-dir data/index/e5-large                   # bake-off variants

Writes `<index-dir>/qdrant/`, `<index-dir>/listings.sqlite`, `<index-dir>/index.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dgbot.core.config import get_settings
from dgbot.core.logging import configure_logging
from dgbot.ingestion.pipeline import build_index
from dgbot.retrieval.embeddings import FastEmbedDense, FastEmbedSparse
from dgbot.retrieval.vectorstore import QdrantStore, open_client


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m dgbot.ingestion", description=__doc__)
    parser.add_argument("--model", default=settings.embedding_model, help="fastembed dense model")
    parser.add_argument("--index-dir", type=Path, default=settings.index_dir)
    args = parser.parse_args(argv)
    configure_logging(settings)

    dense = FastEmbedDense(args.model, cache_dir=settings.embedding_cache_dir)
    sparse = FastEmbedSparse(settings.sparse_model, cache_dir=settings.embedding_cache_dir)
    client = open_client(args.index_dir, settings.qdrant_url)
    store = QdrantStore(client, settings.qdrant_collection)
    try:
        report = build_index(
            settings.processed_data_dir,
            args.index_dir,
            dense,
            sparse,
            store,
            chunk_words=settings.chunk_words,
            overlap_words=settings.chunk_overlap_words,
        )
    finally:
        store.close()
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
