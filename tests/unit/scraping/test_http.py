"""PoliteClient behaviour against an in-memory transport: no network, no real sleeping."""

from collections.abc import Callable

import httpx
import pytest

from dgbot.core.config import Settings
from dgbot.core.errors import FetchError, SourceBlockedError
from dgbot.scraping.http import PoliteClient

Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    """Deterministic clock: `sleep` advances time instead of waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _settings() -> Settings:
    return Settings(_env_file=None, scraper_max_rps=1.0, scraper_max_retries=2)


def _client(handler: Handler, fake: FakeTime) -> PoliteClient:
    return PoliteClient(
        _settings(), transport=httpx.MockTransport(handler), clock=fake.clock, sleep=fake.sleep
    )


def _robots_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    return None


async def test_sends_honest_user_agent_and_checks_robots_first() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _robots_ok(request) or httpx.Response(200, text="ok")

    async with _client(handler, FakeTime()) as client:
        response = await client.get("https://example.com/page")

    assert response.text == "ok"
    assert [r.url.path for r in seen] == ["/robots.txt", "/page"]
    assert all(r.headers["user-agent"].startswith("DarGlobalAssignmentBot/") for r in seen)


async def test_robots_disallow_raises_without_requesting_the_page() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return _robots_ok(request) or httpx.Response(200)

    async with _client(handler, FakeTime()) as client:
        with pytest.raises(SourceBlockedError, match=r"robots\.txt"):
            await client.get("https://example.com/private/x")

    assert paths == ["/robots.txt"]


async def test_requests_to_one_host_are_spaced_by_the_rate_limit() -> None:
    fake = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        return _robots_ok(request) or httpx.Response(200)

    async with _client(handler, fake) as client:
        for i in range(3):
            await client.get(f"https://example.com/{i}")

    # robots + 3 pages at 1 req/s → three 1-second waits.
    assert fake.sleeps == [1.0, 1.0, 1.0]


async def test_retries_503_honouring_retry_after_then_succeeds() -> None:
    fake = FakeTime()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (robots := _robots_ok(request)) is not None:
            return robots
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "7"})
        return httpx.Response(200, text="recovered")

    async with _client(handler, fake) as client:
        response = await client.get("https://example.com/flaky")

    assert response.text == "recovered"
    assert 7.0 in fake.sleeps


async def test_gives_up_after_max_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _robots_ok(request) or httpx.Response(500)

    async with _client(handler, FakeTime()) as client:
        with pytest.raises(FetchError, match="gave up after 3 attempts"):
            await client.get("https://example.com/down")


async def test_403_is_a_block_and_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (robots := _robots_ok(request)) is not None:
            return robots
        calls["n"] += 1
        return httpx.Response(403)

    async with _client(handler, FakeTime()) as client:
        with pytest.raises(SourceBlockedError, match="403"):
            await client.get("https://example.com/")

    assert calls["n"] == 1


async def test_missing_robots_txt_allows_crawling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    async with _client(handler, FakeTime()) as client:
        assert (await client.get("https://cdn.example.com/s.xml.gz")).text == "ok"
