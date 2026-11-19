"""Source interface + registry. Adding a third website = one new module that registers here."""

from __future__ import annotations

from typing import Protocol

from dgbot.core.config import Settings
from dgbot.scraping.models import CollectReport
from dgbot.scraping.storage import RawStore


class Source(Protocol):
    """A website we collect raw pages from. Collection is offline-only (D-003)."""

    name: str

    async def collect(
        self, settings: Settings, store: RawStore, *, limit: int | None, refresh: bool
    ) -> CollectReport:
        """Fetch raw responses into `store`.

        `limit` caps new fetches (for trial runs); `refresh` re-fetches cached URLs.
        Must stop (not escalate) when the site blocks us (D-004).
        """
        ...
