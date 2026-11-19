"""ChatService: question → grounded, cited, streamed answer. Exactly one LLM call (D-044).

language → cache → retrieval query → hybrid retrieve → (listing lookup) → numbered
sources → stream answer → clean citations → cache
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import anyio

from dgbot.chat.cache import AnswerCache
from dgbot.chat.listings_intent import parse_listing_query
from dgbot.chat.prompts import (
    detect_language,
    format_sources,
    system_prompt,
    trimmed_history,
    user_prompt,
)
from dgbot.core.errors import LLMError, LLMQuotaExceededError
from dgbot.domain.chat import ChatAnswer, ChatMessage, SourceRef
from dgbot.domain.text import ascii_digits
from dgbot.llm.base import Delta, Done, LLMClient, Message
from dgbot.retrieval.listings import ListingsDB
from dgbot.retrieval.retriever import HybridRetriever

logger = logging.getLogger(__name__)

_CITATION = re.compile(r"\[(\d+)\]")
# Arabic-Indic citation digits (U+0660-0669, U+06F0-06F9), e.g. an Arabic "[1]".
_ARABIC_CITATION = re.compile("\\[([\u0660-\u0669\u06f0-\u06f9]+)\\]")
_FOLLOW_UP_WORDS = 12
_SNIPPET_CHARS = 240

ERRORS = {
    "quota": {
        "en": "The assistant has used today's free model quota. Please try again later.",
        "ar": "استنفد المساعد الحصة المجانية لهذا اليوم. يرجى المحاولة لاحقاً.",
    },
    "unavailable": {
        "en": "The language model is busy right now. Please try again in a moment.",
        "ar": "نموذج اللغة مشغول حالياً. يرجى المحاولة بعد قليل.",
    },
}


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[SourceRef]
    lang: str


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class DoneEvent:
    answer: ChatAnswer


@dataclass(frozen=True)
class ErrorEvent:
    code: str  # quota | unavailable
    message: str


ChatEvent = SourcesEvent | TokenEvent | DoneEvent | ErrorEvent


class ChatService:
    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLMClient,
        *,
        listings: ListingsDB | None = None,
        cities: dict[str, str] | None = None,
        cache: AnswerCache | None = None,
        top_k: int = 8,
        max_context_words: int = 1_800,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._listings = listings
        self._cities = cities or {}
        self._cache = cache if cache is not None else AnswerCache()
        self._top_k = top_k
        self._max_words = max_context_words

    async def answer(
        self, question: str, history: Sequence[ChatMessage] = ()
    ) -> ChatAnswer | ErrorEvent:
        """Non-streaming: the final answer (JSON endpoint, evaluation)."""
        async for event in self.stream(question, history):
            if isinstance(event, DoneEvent | ErrorEvent):
                return event.answer if isinstance(event, DoneEvent) else event
        raise RuntimeError("chat stream ended without a result")

    async def stream(
        self, question: str, history: Sequence[ChatMessage] = ()
    ) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        question = question.strip()
        lang = detect_language(question)
        history = trimmed_history(history)

        if not history and (cached := self._cache.get(question)):
            yield SourcesEvent(cached.sources, cached.lang)
            yield TokenEvent(cached.answer)
            yield DoneEvent(cached.model_copy(update={"cached": True, "latency_ms": _ms(started)}))
            return

        sources, texts = await self._gather_sources(question, history)
        yield SourcesEvent(sources, lang)

        messages = [Message("system", system_prompt())]
        messages += [Message(m.role, m.content) for m in history]
        messages.append(
            Message("user", user_prompt(question, format_sources(sources, texts), lang))
        )

        parts: list[str] = []
        model: str | None = None
        try:
            async for event in self._llm.stream(messages):
                if isinstance(event, Delta):
                    parts.append(event.text)
                    yield TokenEvent(event.text)
                elif isinstance(event, Done):
                    model = event.model
        except LLMError as exc:
            code = "quota" if isinstance(exc, LLMQuotaExceededError) else "unavailable"
            logger.warning("chat failed (%s): %s", code, exc)
            yield ErrorEvent(code, ERRORS[code][lang])
            return

        text, cited = clean_citations("".join(parts), len(sources))
        final_sources = [s.model_copy(update={"cited": s.n in cited}) for s in sources]
        answer = ChatAnswer(
            answer=text, sources=final_sources, lang=lang, model=model, latency_ms=_ms(started)
        )
        if not history:
            self._cache.put(question, answer)
        logger.info(
            "answered in %d ms by %s with %d sources", answer.latency_ms, model, len(sources)
        )
        yield DoneEvent(answer)

    async def _gather_sources(
        self, question: str, history: Sequence[ChatMessage]
    ) -> tuple[list[SourceRef], list[str]]:
        query = retrieval_query(question, history)
        hits = await anyio.to_thread.run_sync(lambda: self._retriever.search(query, k=self._top_k))

        sources: list[SourceRef] = []
        texts: list[str] = []
        listing_query = parse_listing_query(question, self._cities) if self._listings else None
        if listing_query is not None and self._listings is not None:
            listings = self._listings
            lookup = await anyio.to_thread.run_sync(lambda: listings.lookup(listing_query))
            sources.append(
                _source(
                    1, lookup.title, lookup.url, "wasalt", "listing_db", "wasalt:db", lookup.text
                )
            )
            texts.append(lookup.text)

        by_record: dict[str, int] = {}
        words = sum(len(t.split()) for t in texts)
        for hit in hits:
            chunk = hit.chunk
            size = len(chunk.text.split())
            if words + size > self._max_words and sources:
                break
            words += size
            if chunk.record_id in by_record:  # merge chunks of one record into one source
                index = by_record[chunk.record_id]
                texts[index] += "\n…\n" + chunk.text
                continue
            by_record[chunk.record_id] = len(sources)
            sources.append(
                _source(
                    len(sources) + 1,
                    chunk.title,
                    chunk.url,
                    chunk.source.value,
                    chunk.record_type,
                    chunk.record_id,
                    chunk.text,
                )
            )
            texts.append(chunk.text)
        return sources, texts


def retrieval_query(question: str, history: Sequence[ChatMessage]) -> str:
    """Short follow-ups ("and its amenities?") borrow the previous user question."""
    previous = next((m.content for m in reversed(history) if m.role == "user"), None)
    if previous and len(question.split()) < _FOLLOW_UP_WORDS:
        return f"{previous}\n{question}"
    return question


def clean_citations(text: str, n_sources: int) -> tuple[str, set[int]]:
    """ASCII citation digits, drop references to sources that don't exist."""
    text = _ARABIC_CITATION.sub(lambda m: f"[{ascii_digits(m.group(1))}]", text)
    cited: set[int] = set()

    def keep(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if 1 <= n <= n_sources:
            cited.add(n)
            return match.group(0)
        return ""

    return _CITATION.sub(keep, text).strip(), cited


def _source(
    n: int, title: str, url: str, source: str, record_type: str, record_id: str, text: str
) -> SourceRef:
    body = text.split("\n", 1)[1] if "\n" in text else text
    snippet = " ".join(body.split())[:_SNIPPET_CHARS]
    return SourceRef(
        n=n,
        title=title,
        url=url,
        source=source,
        record_type=record_type,
        record_id=record_id,
        snippet=snippet,
    )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
