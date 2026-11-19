"""Chat domain types shared by the chat service and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_MESSAGE_CHARS = 1_000


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4_000)


class SourceRef(BaseModel):
    """A numbered source shown to the LLM and to the user (citation `[n]`)."""

    model_config = ConfigDict(extra="forbid")
    n: int
    title: str
    url: str
    source: str  # darglobal | wasalt
    record_type: str
    record_id: str
    snippet: str
    cited: bool = False


class ChatAnswer(BaseModel):
    answer: str
    sources: list[SourceRef]
    lang: Literal["en", "ar"]
    model: str | None = None
    cached: bool = False
    latency_ms: int = 0
