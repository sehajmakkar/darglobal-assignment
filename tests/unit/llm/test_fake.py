from dgbot.llm.base import Message
from dgbot.llm.fake import demo_answer


def test_demo_answer_uses_real_source_titles_table_and_citations() -> None:
    prompt = (
        "Question: What is DG1?\n\nSources:\n[1] DG1 — https://darglobal.co.uk/dg1\ntext\n\n"
        "[2] Business Bay — https://x\ntext\n\nAnswer in English, citing sources like [1]."
    )
    answer = demo_answer([Message("system", "rules"), Message("user", prompt)])

    assert "[1]" in answer and "| Source | Citation |" in answer and "DG1" in answer


def test_demo_answer_in_arabic_and_without_sources() -> None:
    arabic = demo_answer(
        [Message("user", "[1] ذا أستيرا — https://x\nt\n\nAnswer in Arabic (العربية)")]
    )
    assert "إجابة تجريبية" in arabic
    assert "don't have" in demo_answer(
        [Message("user", "Question: weather?\n\nSources:\n(no sources)")]
    )
