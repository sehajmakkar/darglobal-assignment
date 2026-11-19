"""On-disk cache of raw responses: one body file + one JSON metadata file per URL.

The store is the hand-off point between collection (Phase 1) and parsing (Phase 2):
parsers read only from here, so they can be re-run any number of times without
touching the source sites again.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from dgbot.scraping.models import FetchMeta

_SAFE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 80


def key_for(url: str) -> str:
    """Stable, filesystem-safe, human-readable key: `<path-slug>-<hash8>`.

    The hash makes keys unique even when slugs collide (e.g. case variants of a URL).
    """
    parts = urlsplit(url)
    slug = _SAFE.sub("-", f"{parts.path}?{parts.query}".lower()).strip("-")[:_MAX_SLUG]
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"{slug or 'root'}-{digest}"


class RawStore:
    """Raw responses for one source under `<root>/<source>/pages/`."""

    def __init__(self, root: Path, source: str) -> None:
        self.dir = root / source / "pages"

    def _meta_path(self, url: str) -> Path:
        return self.dir / f"{key_for(url)}.json"

    def has(self, url: str) -> bool:
        return self._meta_path(url).exists()

    def save(
        self,
        url: str,
        body: bytes,
        *,
        status: int,
        final_url: str | None = None,
        content_type: str | None = None,
        suffix: str = ".html",
        method: str = "http",
        kind: str | None = None,
    ) -> FetchMeta:
        """Write body then metadata (metadata last, so `has()` implies a complete body)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        key = key_for(url)
        body_path = self.dir / f"{key}{suffix}"
        body_path.write_bytes(body)
        meta = FetchMeta(
            url=url,
            final_url=final_url or url,
            status=status,
            fetched_at=datetime.now(UTC),
            content_type=content_type,
            body_file=body_path.name,
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            method=method,
            kind=kind,
        )
        self._meta_path(url).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        return meta

    def load_meta(self, url: str) -> FetchMeta:
        return FetchMeta.model_validate_json(self._meta_path(url).read_text(encoding="utf-8"))

    def load_body(self, meta: FetchMeta) -> bytes:
        return (self.dir / meta.body_file).read_bytes()

    def iter_meta(self) -> Iterator[FetchMeta]:
        """All stored responses, in filename order (deterministic)."""
        if not self.dir.exists():
            return
        for path in sorted(self.dir.glob("*.json")):
            yield FetchMeta.model_validate_json(path.read_text(encoding="utf-8"))
