"""Composition root: the one place that builds concrete implementations (D-016) and hands
them to route handlers through FastAPI dependency injection."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from dgbot.api.ratelimit import RateLimiter
from dgbot.chat.cache import AnswerCache
from dgbot.chat.service import ChatService
from dgbot.core.config import Settings
from dgbot.core.errors import DgbotError
from dgbot.domain.places import CITY_AR
from dgbot.ingestion.pipeline import INDEX_MANIFEST, LISTINGS_DB
from dgbot.retrieval.listings import ListingsDB

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """Long-lived resources, created once at startup and closed on shutdown."""

    chat: ChatService
    index_info: dict[str, Any] = field(default_factory=dict)
    closers: list[Any] = field(default_factory=list)

    def close(self) -> None:
        for resource in self.closers:
            resource.close()


def build_runtime(settings: Settings) -> Runtime:
    """Real implementations. Raises DgbotError if the index or API key is missing."""
    from dgbot.llm.openrouter import OpenRouterClient
    from dgbot.retrieval.embeddings import FastEmbedDense, FastEmbedSparse
    from dgbot.retrieval.retriever import HybridRetriever
    from dgbot.retrieval.vectorstore import QdrantStore, open_client

    manifest_path = settings.index_dir / INDEX_MANIFEST
    if not manifest_path.exists():
        raise DgbotError(
            f"no search index at {settings.index_dir} — run `python -m dgbot.ingestion`"
        )
    info = json.loads(manifest_path.read_text())
    dense = FastEmbedDense(info["embedding_model"], cache_dir=settings.embedding_cache_dir)
    sparse = FastEmbedSparse(info["sparse_model"], cache_dir=settings.embedding_cache_dir)
    store = QdrantStore(
        open_client(settings.index_dir, settings.qdrant_url), settings.qdrant_collection
    )
    retriever = HybridRetriever(
        dense,
        sparse,
        store,
        top_k=settings.chat_sources_k,
        prefetch_k=settings.retrieval_prefetch_k,
    )
    listings = ListingsDB(settings.index_dir / LISTINGS_DB)
    chat = ChatService(
        retriever,
        OpenRouterClient(settings),
        listings=listings,
        cities=city_spellings(listings.cities()),
        cache=AnswerCache(),
        top_k=settings.chat_sources_k,
        max_context_words=settings.chat_max_context_words,
    )
    return Runtime(chat=chat, index_info=info, closers=[store, listings])


def city_spellings(cities: list[str]) -> dict[str, str]:
    """English names from the data + Arabic names + known short forms → canonical name."""
    spellings = {c: c for c in cities}
    spellings.update({ar: en for en, ar in CITY_AR.items() if en in spellings})
    for city in cities:
        if city.startswith("Al "):
            spellings.setdefault(city[3:], city)  # "Khobar" → "Al Khobar"
    return spellings


def get_app_settings(request: Request) -> Settings:
    """Settings the app was created with (lets tests inject their own)."""
    settings: Settings = request.app.state.settings
    return settings


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime | None = request.app.state.runtime
    if runtime is None:
        raise HTTPException(503, detail=request.app.state.runtime_error or "service not ready")
    return runtime


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter
