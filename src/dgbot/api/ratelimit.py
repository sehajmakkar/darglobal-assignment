"""Per-IP sliding-window rate limit (D-045). In-memory: fine for one container.

Protects the shared 50-requests/day free LLM quota from one heavy user or a bot. With
several replicas this moves to Redis; the interface stays the same.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

_WINDOWS = (("minute", 60.0), ("day", 86_400.0))


class RateLimiter:
    def __init__(
        self, per_minute: int, per_day: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limits = {"minute": per_minute, "day": per_day}
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str) -> tuple[bool, int]:
        """(allowed, retry_after_seconds). Records the hit only when allowed."""
        now = self._clock()
        hits = self._hits[client]
        while hits and now - hits[0] > _WINDOWS[-1][1]:
            hits.popleft()
        for name, span in _WINDOWS:
            limit = self._limits[name]
            if not limit:
                continue
            recent = [t for t in hits if now - t <= span]
            if len(recent) >= limit:
                return False, int(span - (now - recent[0])) + 1
        hits.append(now)
        return True, 0


def client_ip(request: Request) -> str:
    """First hop of X-Forwarded-For (Cloud Run's proxy sets it), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
