"""Application settings.

This is the only module that reads environment variables. Every other module
receives a `Settings` instance (directly or via dependency injection), which keeps
configuration explicit and makes tests trivial to isolate.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated configuration loaded from env vars / `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="DGBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Runtime ──────────────────────────────────────────────────────
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = Field(default=7860, validation_alias="PORT")
    host: str = "0.0.0.0"  # the container must listen on all interfaces
    # Directory served at "/". Defaults to the bundled placeholder page; Phase 5 points it
    # at the built React app (frontend/dist).
    static_dir: Path = Path(__file__).resolve().parent.parent / "api" / "static"

    # ── OpenRouter ───────────────────────────────────────────────────
    # One key (OPENROUTER_API_KEY) or a comma-separated pool (OPENROUTER_API_KEYS);
    # the client fails over to the next key on HTTP 429 (D-015). Free-tier limits are
    # per *account*, so keys from one account share a single daily quota.
    openrouter_api_keys: Annotated[list[SecretStr], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Primary model first, then fallbacks (D-010). Model ids are config, never literals in code.
    # Order from live endpoint status (D-043): Gemma's free endpoint reported no uptime,
    # Nvidia's free endpoints 100%. OpenRouter tries them server-side in this order.
    llm_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "nvidia/nemotron-3.5-super-vl:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "google/gemma-4-31b-it:free",
            "openrouter/free",
        ]
    )
    llm_timeout_s: float = Field(default=60.0, gt=0)
    # Reasoning models spend tokens thinking before answering (C-006): generous budget,
    # low effort, reasoning text excluded from the stream.
    llm_max_tokens: int = Field(default=1_500, ge=200, le=8_000)
    llm_reasoning_effort: Literal["low", "medium", "high"] = "low"
    llm_temperature: float = Field(default=0.2, ge=0, le=1)
    # Sent as HTTP-Referer / X-Title so OpenRouter can attribute traffic to the app.
    app_url: str = "https://github.com/sehajmakkar/darglobal-assignment"
    app_title: str = "DarGlobal x Wasalt Assistant"

    # ── Scraping (offline) ───────────────────────────────────────────
    scraper_user_agent: str = (
        "DarGlobalAssignmentBot/0.1 (hiring assignment; "
        "+https://github.com/sehajmakkar/darglobal-assignment)"
    )
    scraper_max_rps: float = Field(default=1.0, gt=0, le=2.0)  # hard cap: D-004
    scraper_timeout_s: float = Field(default=30.0, gt=0)
    scraper_max_retries: int = Field(default=3, ge=0, le=5)
    # Pause between DarGlobal pages in the real browser (D-020: 3-5 s, human pace).
    scraper_browser_delay_s: float = Field(default=4.0, ge=3.0, le=10.0)
    # Raw responses (HTML, sitemaps) + fetch metadata. Git-ignored; never shipped.
    raw_data_dir: Path = Path("data/raw")
    # Processed snapshot (committed, D-006): what the Docker image is built from.
    processed_data_dir: Path = Path("data/processed")

    # ── Indexing & retrieval (Phase 3) ───────────────────────────────
    index_dir: Path = Path("data/index")  # git-ignored; built from the snapshot
    qdrant_url: str | None = None  # None → embedded local mode in index_dir (D-009)
    qdrant_collection: str = "dgbot"
    # Bake-off winner (D-042): best MRR, Arabic 1.00, half the size of e5-large.
    embedding_model: str = "google/embeddinggemma-300m"
    sparse_model: str = "Qdrant/bm25"
    embedding_cache_dir: Path | None = None  # fastembed model cache (baked into the image)
    chunk_words: int = Field(default=200, ge=50, le=600)
    chunk_overlap_words: int = Field(default=40, ge=0, le=200)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_prefetch_k: int = Field(default=40, ge=5, le=200)  # per branch, before fusion

    # ── Chat API (Phase 4) ───────────────────────────────────────────
    chat_sources_k: int = Field(default=8, ge=1, le=20)  # chunks retrieved per question
    chat_max_context_words: int = Field(default=1_800, ge=200, le=8_000)
    # Per client IP; protects the 50/day free quota (D-015). 0 disables a limit.
    rate_limit_per_minute: int = Field(default=6, ge=0)
    rate_limit_per_day: int = Field(default=40, ge=0)

    @field_validator("openrouter_api_keys", "llm_models", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, cached. Tests should construct `Settings(...)` directly."""
    return Settings()
