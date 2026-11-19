"""Retrieval metrics on eval/golden.jsonl against a built index.

    uv run python -m dgbot.evaluation                                  # Settings' index/model
    uv run python -m dgbot.evaluation --index-dir data/index/e5-large  # a bake-off variant
    uv run python -m dgbot.evaluation --answers --limit 10             # LLM answers: uses quota!

The embedding model is read from the index's `index.json`, so queries are always embedded
with the same model as the documents.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dgbot.core.config import Settings, get_settings
from dgbot.core.logging import configure_logging
from dgbot.evaluation.retrieval import (
    GoldenItem,
    evaluate,
    format_report,
    load_golden,
    to_json,
    unknown_expected,
)
from dgbot.ingestion.pipeline import INDEX_MANIFEST
from dgbot.retrieval.embeddings import FastEmbedDense, FastEmbedSparse
from dgbot.retrieval.retriever import HybridRetriever
from dgbot.retrieval.vectorstore import QdrantStore, open_client


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m dgbot.evaluation", description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=settings.index_dir)
    parser.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    parser.add_argument("--out", type=Path, default=None, help="write per-question JSON here")
    parser.add_argument("--answers", action="store_true", help="evaluate full LLM answers")
    parser.add_argument("--limit", type=int, default=None, help="answer eval: max questions")
    args = parser.parse_args(argv)
    configure_logging(settings)

    manifest = json.loads((args.index_dir / INDEX_MANIFEST).read_text())
    dense = FastEmbedDense(manifest["embedding_model"], cache_dir=settings.embedding_cache_dir)
    sparse = FastEmbedSparse(manifest["sparse_model"], cache_dir=settings.embedding_cache_dir)
    store = QdrantStore(
        open_client(args.index_dir, settings.qdrant_url), settings.qdrant_collection
    )
    retriever = HybridRetriever(
        dense,
        sparse,
        store,
        top_k=settings.retrieval_top_k,
        prefetch_k=settings.retrieval_prefetch_k,
    )
    items = load_golden(args.golden)

    if bad := unknown_expected(items, store.record_ids()):
        print("Golden set references records that are not in the index:\n  " + "\n  ".join(bad))
        return 2

    if args.answers:
        return _answers(settings, items[: args.limit] if args.limit else items, store, args.out)

    report = evaluate(retriever, items)
    print(format_report(report, f"{manifest['embedding_model']} ({manifest['chunks']} chunks)"))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(to_json(report) + "\n", encoding="utf-8")
    store.close()
    return 0


def _answers(
    settings: Settings, items: list[GoldenItem], store: QdrantStore, out: Path | None
) -> int:
    import asyncio

    from dgbot.api.dependencies import build_runtime
    from dgbot.evaluation.answers import evaluate_answers, summarize

    store.close()  # the runtime opens its own client on the same index directory
    print(f"Answer eval: {len(items)} LLM requests (free quota: 50/day).")
    runtime = build_runtime(settings)
    try:
        results = asyncio.run(evaluate_answers(runtime.chat, items))
    finally:
        runtime.close()
    print(summarize(results))
    if out:
        rows = [
            {
                "id": r.item.id,
                "question": r.item.question,
                "model": r.model,
                "error": r.error,
                "checks": r.checks,
                "answer": r.answer,
            }
            for r in results
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
