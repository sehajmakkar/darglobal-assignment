"""FakeLLMClient: deterministic answers for tests and offline dev — never uses quota."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence

from dgbot.llm.base import Delta, Done, Message, StreamEvent

Responder = Callable[[Sequence[Message]], str]


def echo_sources(messages: Sequence[Message]) -> str:
    """Default fake answer: cite the first source the prompt contains."""
    prompt = messages[-1].content
    return (
        "According to the sources [1], here is the answer."
        if "[1]" in prompt
        else ("I don't have that information in my data.")
    )


class FakeLLMClient:
    def __init__(
        self,
        responder: Responder | str = echo_sources,
        *,
        error: Exception | None = None,
        model: str = "fake/model",
    ) -> None:
        self._responder = responder
        self._error = error
        self._model = model
        self.calls: list[list[Message]] = []

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[StreamEvent]:
        self.calls.append(list(messages))
        if self._error is not None:
            raise self._error
        text = self._responder if isinstance(self._responder, str) else self._responder(messages)
        for word in text.split(" "):
            yield Delta(word + " ")
        yield Done(model=self._model, prompt_tokens=100, completion_tokens=len(text.split()))


def demo_answer(messages: Sequence[Message]) -> str:
    """Offline demo answer built from the real retrieved sources (DGBOT_LLM_FAKE=1).

    Exercises every UI feature — paragraphs, bullet list, table, citations — at zero quota.
    """
    import re

    prompt = messages[-1].content
    titles = re.findall(r"^\[(\d+)\] (.+?) — ", prompt, re.M)
    if not titles:
        return "I don't have information about that in my sources."
    arabic = "Answer in Arabic" in prompt
    rows = "\n".join(f"| {title[:60]} | [{n}] |" for n, title in titles[:4])
    if arabic:
        return (
            f"هذه إجابة تجريبية (وضع العرض دون اتصال) مبنية على المصادر المسترجعة [1].\n\n"
            f"- أهم مصدر: {titles[0][1]} [1]\n"
            f"- مصادر أخرى ذات صلة [2][3]\n\n"
            f"| المصدر | الإشارة |\n|---|---|\n{rows}"
        )
    return (
        f"This is an **offline demo answer** built from the retrieved sources [1].\n\n"
        f"- Top match: {titles[0][1]} [1]\n"
        f"- Other relevant sources [2][3]\n\n"
        f"| Source | Citation |\n|---|---|\n{rows}\n\n"
        f"Real answers come from a free OpenRouter model."
    )
