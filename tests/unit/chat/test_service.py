from datetime import UTC, datetime
from pathlib import Path

from dgbot.chat.cache import AnswerCache, normalize_question
from dgbot.chat.prompts import detect_language
from dgbot.chat.service import (
    ChatService,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    clean_citations,
    retrieval_query,
)
from dgbot.core.errors import LLMUnavailableError
from dgbot.domain.chat import ChatAnswer, ChatMessage
from dgbot.domain.models import Listing, Source
from dgbot.ingestion.listings_db import build_listings_db
from dgbot.llm.fake import FakeLLMClient
from dgbot.retrieval.listings import ListingsDB
from tests.support.runtime import fake_retriever


def _service(llm: FakeLLMClient, **kw: object) -> ChatService:
    return ChatService(fake_retriever(), llm, top_k=3, **kw)  # type: ignore[arg-type]


async def test_answer_is_grounded_cited_and_cached() -> None:
    llm = FakeLLMClient()
    service = _service(llm, cache=AnswerCache())

    first = await service.answer("Tell me about The Astera")
    second = await service.answer("tell me about the astera?")  # same question, normalised

    assert isinstance(first, ChatAnswer) and isinstance(second, ChatAnswer)
    assert "[1]" in first.answer and first.sources[0].cited
    assert second.cached and len(llm.calls) == 1  # cache hit spent no quota


async def test_prompt_contains_rules_sources_language_and_history() -> None:
    llm = FakeLLMClient()
    history = [
        ChatMessage(role="user", content="What is DG1?"),
        ChatMessage(role="assistant", content="A tower [1]."),
    ]

    await _service(llm).answer("وما هي مرافقه؟", history)

    system, *middle, user = llm.calls[0]
    assert "DarGlobal prices are not published" in system.content
    assert [m.content for m in middle] == ["What is DG1?", "A tower [1]."]
    assert "Answer in Arabic" in user.content and "[1]" in user.content


async def test_listing_question_adds_exact_database_source(tmp_path: Path) -> None:
    now = datetime(2026, 11, 20, tzinfo=UTC)
    rows = [
        Listing(
            id=f"wasalt:listing:{i}",
            source=Source.WASALT,
            url=f"https://w/{i}",
            scraped_at=now,
            listing_id=str(i),
            purpose="rent",
            property_type="villa",
            bedrooms=4,
        )
        for i in range(7)
    ]
    build_listings_db(tmp_path / "l.sqlite", rows)
    llm = FakeLLMClient()
    service = _service(llm, listings=ListingsDB(tmp_path / "l.sqlite"), cities={"Riyadh": "Riyadh"})

    events = [e async for e in service.stream("4-bed villas for rent in Riyadh")]

    sources = next(e for e in events if isinstance(e, SourcesEvent)).sources
    assert sources[0].record_type == "listing_db" and sources[0].n == 1
    assert "Matching listings across Saudi Arabia: 7" in llm.calls[0][-1].content
    assert isinstance(events[-1], DoneEvent)


async def test_llm_failure_becomes_a_localised_error_event() -> None:
    service = _service(FakeLLMClient(error=LLMUnavailableError("down")))
    result = await service.answer("ما هو مشروع دي جي ون؟")
    assert (
        isinstance(result, ErrorEvent)
        and result.code == "unavailable"
        and "نموذج" in result.message
    )


def test_retrieval_query_borrows_previous_question_for_short_follow_ups() -> None:
    history = [ChatMessage(role="user", content="Tell me about W Residences")]
    assert (
        retrieval_query("and its amenities?", history)
        == "Tell me about W Residences\nand its amenities?"
    )
    long_q = "What are the payment plans and handover dates for every DarGlobal project in Oman"
    assert retrieval_query(long_q, history) == long_q


def test_clean_citations() -> None:
    assert clean_citations("A [1][9] B [٢]", 2) == ("A [1] B [2]", {1, 2})


def test_language_and_normalisation() -> None:
    assert detect_language("شقق للإيجار في الرياض") == "ar"
    assert detect_language("Apartments in الرياض please") == "en"
    assert normalize_question("  What is DG1?! ") == normalize_question("what is dg1")
