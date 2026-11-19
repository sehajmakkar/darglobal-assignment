"""Prompt assembly. Templates live in `chat/prompts/*.md` (versioned files, not strings)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache
from importlib.resources import files
from typing import Literal

from dgbot.domain.chat import ChatMessage, SourceRef

Lang = Literal["en", "ar"]
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_LANG_NAME = {"en": "English", "ar": "Arabic (العربية)"}
_HISTORY_MESSAGES = 4
_HISTORY_CHARS = 600


@cache
def system_prompt() -> str:
    return (files("dgbot.chat") / "prompts" / "system.md").read_text(encoding="utf-8").strip()


def detect_language(text: str) -> Lang:
    """Arabic if most letters are Arabic script; otherwise English."""
    letters = _LETTER.findall(text)
    if not letters:
        return "en"
    arabic = sum(1 for ch in letters if _ARABIC.match(ch))
    return "ar" if arabic / len(letters) >= 0.3 else "en"


def format_sources(sources: Sequence[SourceRef], texts: Sequence[str]) -> str:
    blocks = [
        f"[{s.n}] {s.title} — {s.url}\n{text}" for s, text in zip(sources, texts, strict=True)
    ]
    return "\n\n".join(blocks)


def user_prompt(question: str, sources_block: str, lang: Lang) -> str:
    sources = sources_block or "(no sources found for this question)"
    return (
        f"Question: {question}\n\n"
        f"Sources:\n{sources}\n\n"
        f"Answer in {_LANG_NAME[lang]}, citing sources like [1]."
    )


def trimmed_history(history: Sequence[ChatMessage]) -> list[ChatMessage]:
    """The last few turns, shortened: context for follow-ups without eating the budget."""
    recent = list(history)[-_HISTORY_MESSAGES:]
    return [
        ChatMessage(role=m.role, content=m.content[:_HISTORY_CHARS])
        for m in recent
        if m.content.strip()
    ]
