"""Answer cache: identical first-turn questions are answered without spending quota (D-015).

In-memory LRU with a TTL — good enough for one container; swap for Redis if the API is
scaled out. Only first-turn questions are cached (follow-ups depend on history).
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import OrderedDict

from dgbot.domain.chat import ChatAnswer
from dgbot.domain.text import ascii_digits

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKC", ascii_digits(question)).casefold()
    return _SPACE.sub(" ", _PUNCT.sub(" ", text)).strip()


class AnswerCache:
    def __init__(self, max_entries: int = 512, ttl_s: float = 24 * 3600) -> None:
        self._entries: OrderedDict[str, tuple[float, ChatAnswer]] = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_s

    def get(self, question: str) -> ChatAnswer | None:
        key = normalize_question(question)
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, answer = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return answer

    def put(self, question: str, answer: ChatAnswer) -> None:
        key = normalize_question(question)
        self._entries[key] = (time.monotonic(), answer)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
