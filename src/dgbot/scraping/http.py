"""PoliteClient: the only way the scrapers make plain HTTP requests (D-004).

- honest User-Agent from Settings
- robots.txt checked per host before any other request (RFC 9309 semantics)
- per-host rate limit (≤ `scraper_max_rps`, hard-capped at 2 req/s in Settings)
- retries with exponential backoff on network errors, 429 and 5xx; honours Retry-After
- 403 from the server is a *block*, never retried → SourceBlockedError
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from dgbot.core.config import Settings
from dgbot.core.errors import FetchError, SourceBlockedError
from dgbot.scraping.robots import RobotsPolicy

logger = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_S = 60.0


class PoliteClient:
    """Async HTTP client that enforces our scraping rules. Use as `async with`."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._min_interval = 1.0 / settings.scraper_max_rps
        self._clock = clock
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.scraper_user_agent},
            timeout=settings.scraper_timeout_s,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotsPolicy] = {}
        self._last_request: dict[str, float] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get(self, url: str) -> httpx.Response:
        """GET a URL after the robots check. Raises SourceBlockedError / FetchError."""
        policy = await self.robots_for(url)
        if not policy.allowed(url):
            raise SourceBlockedError(url, "disallowed by robots.txt")
        response = await self._get_with_retries(url)
        if response.status_code == 403:
            raise SourceBlockedError(url, "HTTP 403 (blocked by the server)")
        return response

    async def robots_for(self, url: str) -> RobotsPolicy:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host not in self._robots:
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            ua = self._settings.scraper_user_agent
            try:
                response = await self._get_with_retries(robots_url)
            except FetchError:
                self._robots[host] = RobotsPolicy.from_status(503, ua)  # unreachable
            else:
                if response.is_success:
                    self._robots[host] = RobotsPolicy.from_text(response.text, ua)
                else:
                    self._robots[host] = RobotsPolicy.from_status(response.status_code, ua)
                logger.info("robots.txt for %s: HTTP %d", host, response.status_code)
        return self._robots[host]

    async def _throttle(self, host: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last_request.get(host)
            if last is not None:
                wait = self._min_interval - (self._clock() - last)
                if wait > 0:
                    await self._sleep(wait)
            self._last_request[host] = self._clock()

    async def _get_with_retries(self, url: str) -> httpx.Response:
        host = urlsplit(url).netloc.lower()
        attempts = self._settings.scraper_max_retries + 1
        last_error = "no attempt made"
        for attempt in range(1, attempts + 1):
            await self._throttle(host)
            try:
                response = await self._client.get(url)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                delay = 2.0**attempt
            else:
                if response.status_code not in _RETRY_STATUSES:
                    return response
                last_error = f"HTTP {response.status_code}"
                delay = _retry_after(response) or 2.0**attempt
            if attempt < attempts:
                logger.warning("retry %d/%d for %s (%s)", attempt, attempts - 1, url, last_error)
                await self._sleep(delay)
        raise FetchError(url, f"gave up after {attempts} attempts: {last_error}")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return min(float(value), _MAX_RETRY_AFTER_S)
    except ValueError:
        return None  # HTTP-date form: fall back to exponential backoff
