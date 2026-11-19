from dgbot.chat.cache import AnswerCache
from dgbot.chat.service import ChatService
from dgbot.evaluation.answers import evaluate_answers, summarize
from dgbot.evaluation.retrieval import GoldenItem
from dgbot.llm.fake import FakeLLMClient
from tests.support.runtime import fake_retriever


async def test_answer_checks_with_fake_llm() -> None:
    items = [
        GoldenItem(
            id="a",
            question="Tell me about The Astera",
            lang="en",
            category="darglobal",
            expected=["darglobal:project:the-astera"],
        ),
        GoldenItem(
            id="p",
            question="Price of DG1?",
            lang="en",
            category="darglobal",
            expected=["darglobal:project:dg1"],
        ),
    ]
    responses = iter(
        ["The Astera is on Al Marjan Island [1].", "DG1 starts at AED 1.2 million [1]."]
    )
    service = ChatService(
        fake_retriever(), FakeLLMClient(lambda _: next(responses)), cache=AnswerCache(), top_k=3
    )

    results = await evaluate_answers(service, items)

    assert results[0].checks == {"language": True, "grounded": True, "no_dg_price": True}
    assert (
        results[1].checks is not None and results[1].checks["no_dg_price"] is False
    )  # D-037 caught
    assert "no_dg_price" in summarize(results)


def test_unit_price_check_ignores_company_and_regulatory_figures() -> None:
    from dgbot.evaluation.answers import unit_price_mentions

    assert unit_price_mentions("Apartments at DG1 start from AED 1.2 million [1].")
    assert unit_price_mentions("الشقق يبدأ سعرها من 900 ألف درهم")
    for fine in [
        "Revenue rose to US$258.0 million from US$155.4 million [1].",
        "It has a gross development value of AED 900 million [5].",
        "Invest at least SAR 4 million for residency [1].",
        "قيمة التطوير الإجمالية 900 مليون درهم",
    ]:
        assert unit_price_mentions(fine) == [], fine
