"""Data shapes produced by the scraping layer (offline only, D-003)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SitemapEntry(BaseModel):
    """One `<url>` (or `<sitemap>`) entry from a sitemap file."""

    url: str
    lastmod: str | None = None


class FetchMeta(BaseModel):
    """Everything we know about one stored response. Saved next to the body as JSON."""

    url: str
    final_url: str
    status: int
    fetched_at: datetime
    content_type: str | None = None
    body_file: str
    bytes: int
    sha256: str
    method: str = Field(description="'http' (PoliteClient) or 'browser' (Playwright, D-020)")
    kind: str | None = Field(default=None, description="source-specific URL classification")


class CollectReport(BaseModel):
    """Summary of one collector run, printed by the CLI."""

    source: str
    discovered: int = 0
    fetched: int = 0
    cached: int = 0
    skipped: int = 0
    failed: list[str] = Field(default_factory=list)
    stopped_reason: str | None = None
