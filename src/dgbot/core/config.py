"""Application settings.

This is the only module that reads environment variables. Every other module
receives a `Settings` instance (directly or via dependency injection), which keeps
configuration explicit and makes tests trivial to isolate.
"""

from __future__ import annotations

from functools import lru_cache
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
    llm_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3.5-super-vl:free",
            "openrouter/free",
        ]
    )
    llm_timeout_s: float = Field(default=60.0, gt=0)
    # Sent as HTTP-Referer / X-Title so OpenRouter can attribute traffic to the app.
    app_url: str = "https://github.com/sehajmakkar/darglobal-assignment"
    app_title: str = "DarGlobal x Wasalt Assistant"

    # ── Scraping (offline) ───────────────────────────────────────────
    scraper_user_agent: str = (
        "DarGlobalAssignmentBot/0.1 (hiring assignment; "
        "+https://github.com/sehajmakkar/darglobal-assignment)"
    )
    scraper_max_rps: float = Field(default=1.0, gt=0, le=2.0)  # hard cap: D-004

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
