"""OpenRouter client (free `:free` models via the OpenAI-compatible API, D-010).

Behaviour, in order of what can go wrong with free models:
- **Model fallback** is server-side: we send the whole chain as OpenRouter's `models`.
- **Empty answers** (a reasoning model spent its budget thinking — C-006) count as a
  failure: retry once without the model that came back empty.
- **429 / daily cap** on a key → mark it exhausted until the next UTC day, try the next
  key in the pool (D-015); none left → `LLMQuotaExceededError`.
- **Timeouts / provider errors** → `LLMUnavailableError`.
- Once text has been streamed to the user we never switch models silently.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, date, datetime
from typing import Any

import openai
from openai import AsyncOpenAI

from dgbot.core.config import Settings
from dgbot.core.errors import LLMQuotaExceededError, LLMUnavailableError
from dgbot.llm.base import Delta, Done, Message, StreamEvent

logger = logging.getLogger(__name__)

ClientFactory = Callable[[str], Any]  # api key → object with `.chat.completions.create`
# OpenRouter rejects a `models` fallback list longer than 3 with HTTP 400 (C-020).
MAX_FALLBACK_MODELS = 3


class OpenRouterClient:
    def __init__(self, settings: Settings, *, client_factory: ClientFactory | None = None) -> None:
        if not settings.openrouter_api_keys:
            raise LLMUnavailableError("no OpenRouter API key configured (OPENROUTER_API_KEY)")
        self._settings = settings
        self._keys = [k.get_secret_value() for k in settings.openrouter_api_keys]
        self._exhausted: dict[int, date] = {}  # key index → UTC day it hit the cap
        factory = client_factory or self._default_factory
        self._clients = [factory(key) for key in self._keys]

    def _default_factory(self, key: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=key,
            base_url=self._settings.openrouter_base_url,
            timeout=self._settings.llm_timeout_s,
            max_retries=1,
            default_headers={
                "HTTP-Referer": self._settings.app_url,
                "X-Title": self._settings.app_title,
            },
        )

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[StreamEvent]:
        models = list(self._settings.llm_models)
        for attempt in range(2):  # second attempt only after an empty answer
            produced_text = False
            async for event in self._stream_with_key_failover(messages, models):
                if isinstance(event, Delta):
                    produced_text = True
                    yield event
                elif produced_text:
                    yield event
                    return
                else:
                    logger.warning("empty answer from %s (attempt %d)", event.model, attempt + 1)
                    models = [m for m in models if m != event.model] or models
                    break
        raise LLMUnavailableError("the models returned empty answers")

    async def _stream_with_key_failover(
        self, messages: Sequence[Message], models: list[str]
    ) -> AsyncIterator[StreamEvent]:
        today = datetime.now(UTC).date()
        for index, client in enumerate(self._clients):
            if self._exhausted.get(index) == today:
                continue
            try:
                async for event in self._stream_once(client, messages, models):
                    yield event
                return
            except openai.RateLimitError as exc:
                logger.warning("key #%d rate-limited: %s", index + 1, _short(exc))
                self._exhausted[index] = today
            except openai.APIStatusError as exc:
                if exc.status_code == 402:  # out of credits / free cap on this key
                    self._exhausted[index] = today
                    continue
                raise LLMUnavailableError(
                    f"provider error {exc.status_code}: {_short(exc)}"
                ) from exc
            except (openai.APITimeoutError, openai.APIConnectionError) as exc:
                raise LLMUnavailableError(f"provider unreachable: {_short(exc)}") from exc
        raise LLMQuotaExceededError("daily free-model quota reached on all configured keys")

    async def _stream_once(
        self, client: Any, messages: Sequence[Message], models: list[str]
    ) -> AsyncIterator[StreamEvent]:
        started = time.perf_counter()
        models = models[:MAX_FALLBACK_MODELS]
        stream = await client.chat.completions.create(
            model=models[0],
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=self._settings.llm_max_tokens,
            temperature=self._settings.llm_temperature,
            extra_body={
                "models": models,  # OpenRouter server-side fallback chain
                "reasoning": {"effort": self._settings.llm_reasoning_effort, "exclude": True},
            },
        )
        served = models[0]
        usage: Any = None
        async for chunk in stream:
            served = getattr(chunk, "model", None) or served
            usage = getattr(chunk, "usage", None) or usage
            for choice in getattr(chunk, "choices", None) or []:
                text = getattr(choice.delta, "content", None)
                if text:
                    yield Delta(text)
        logger.info("LLM served by %s in %.1fs", served, time.perf_counter() - started)
        yield Done(
            model=served,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )


def _short(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:200]
