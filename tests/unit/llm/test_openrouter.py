"""OpenRouterClient control flow with a fake SDK client: no network, no quota."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import openai
import pytest

from dgbot.core.config import Settings
from dgbot.core.errors import LLMQuotaExceededError, LLMUnavailableError
from dgbot.llm.base import Delta, Done, Message
from dgbot.llm.openrouter import OpenRouterClient

MSGS = [Message("user", "hi")]


@dataclass
class _Choice:
    delta: Any


@dataclass
class _Chunk:
    model: str
    choices: list[_Choice]
    usage: Any = None


@dataclass
class _Delta:
    content: str | None


@dataclass
class FakeSDK:
    """Mimics `client.chat.completions.create(...)` returning an async stream."""

    script: list[Any]  # per call: list[str] (tokens) | Exception
    model: str = "nvidia/model-a:free"
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def chat(self) -> "FakeSDK":
        return self

    @property
    def completions(self) -> "FakeSDK":
        return self

    async def create(self, **kwargs: Any) -> AsyncIterator[_Chunk]:
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        served = kwargs["model"]

        async def gen() -> AsyncIterator[_Chunk]:
            for token in step:
                yield _Chunk(served, [_Choice(_Delta(token))])
            yield _Chunk(
                served, [], usage=type("U", (), {"prompt_tokens": 10, "completion_tokens": 3})()
            )

        return gen()


def _settings(keys: str = "k1") -> Settings:
    return Settings(_env_file=None, OPENROUTER_API_KEYS=keys, llm_models=["m/a:free", "m/b:free"])


def _rate_limit() -> openai.RateLimitError:
    request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return openai.RateLimitError(
        "Rate limit exceeded: free-models-per-day",
        response=httpx2.Response(429, request=request),
        body=None,
    )


async def _collect(client: OpenRouterClient) -> list[Any]:
    return [e async for e in client.stream(MSGS)]


async def test_streams_text_then_done_with_served_model_and_fallback_chain() -> None:
    sdk = FakeSDK([["Hello", " world"]])
    client = OpenRouterClient(_settings(), client_factory=lambda _: sdk)

    events = await _collect(client)

    assert [e.text for e in events if isinstance(e, Delta)] == ["Hello", " world"]
    assert isinstance(events[-1], Done) and events[-1].model == "m/a:free"
    sent = sdk.calls[0]
    assert sent["extra_body"]["models"] == ["m/a:free", "m/b:free"]
    assert sent["extra_body"]["reasoning"] == {"effort": "low", "exclude": True}
    assert sent["stream"] is True


async def test_empty_answer_retries_without_that_model() -> None:
    sdk = FakeSDK([[], ["answer"]])
    client = OpenRouterClient(_settings(), client_factory=lambda _: sdk)

    events = await _collect(client)

    assert "".join(e.text for e in events if isinstance(e, Delta)) == "answer"
    assert sdk.calls[1]["extra_body"]["models"] == ["m/b:free"]


async def test_two_empty_answers_raise_unavailable() -> None:
    client = OpenRouterClient(_settings(), client_factory=lambda _: FakeSDK([[], []]))
    with pytest.raises(LLMUnavailableError, match="empty"):
        await _collect(client)


async def test_rate_limited_key_fails_over_to_next_key() -> None:
    sdks = {"k1": FakeSDK([_rate_limit()]), "k2": FakeSDK([["ok"]])}
    client = OpenRouterClient(_settings("k1,k2"), client_factory=lambda key: sdks[key])

    events = await _collect(client)

    assert "".join(e.text for e in events if isinstance(e, Delta)) == "ok"


async def test_all_keys_rate_limited_is_a_quota_error_and_key_stays_skipped() -> None:
    sdk = FakeSDK([_rate_limit()])
    client = OpenRouterClient(_settings(), client_factory=lambda _: sdk)

    with pytest.raises(LLMQuotaExceededError):
        await _collect(client)
    with pytest.raises(LLMQuotaExceededError):  # same UTC day: not even attempted again
        await _collect(client)
    assert len(sdk.calls) == 1


async def test_timeout_is_unavailable() -> None:
    request = httpx2.Request("POST", "https://openrouter.ai")
    client = OpenRouterClient(
        _settings(), client_factory=lambda _: FakeSDK([openai.APITimeoutError(request)])
    )
    with pytest.raises(LLMUnavailableError, match="unreachable"):
        await _collect(client)


def test_missing_key_is_a_clear_error() -> None:
    with pytest.raises(LLMUnavailableError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(Settings(_env_file=None, OPENROUTER_API_KEYS=""))


async def test_sends_at_most_three_fallback_models() -> None:
    sdk = FakeSDK([[], ["ok"]])
    settings = Settings(
        _env_file=None, OPENROUTER_API_KEYS="k", llm_models=["a", "b", "c", "d", "e"]
    )
    client = OpenRouterClient(settings, client_factory=lambda _: sdk)

    await _collect(client)

    assert sdk.calls[0]["extra_body"]["models"] == ["a", "b", "c"]  # OpenRouter's limit (C-020)
    assert sdk.calls[1]["extra_body"]["models"] == ["b", "c", "d"]  # after "a" came back empty
