"""LLM client interface. The chat layer depends on this, never on a provider SDK."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class Delta:
    """A piece of streamed answer text."""

    text: str


@dataclass(frozen=True)
class Done:
    """End of a stream: which model actually answered (free routing varies — C-006)."""

    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


StreamEvent = Delta | Done


class LLMClient(Protocol):
    def stream(self, messages: Sequence[Message]) -> AsyncIterator[StreamEvent]:
        """Yield `Delta`s then exactly one `Done`. Raise `LLMError` subclasses on failure."""
        ...
