"""HTTP request/response DTOs. Kept separate from domain models so the API can evolve
without leaking internals (and vice versa)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from dgbot.domain.chat import MAX_MESSAGE_CHARS, ChatMessage


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    env: str
    ready: bool = Field(description="search index + LLM client loaded")
    warming_up: bool = Field(default=False, description="still loading after a cold start")
    detail: str | None = None
    index: dict[str, Any] | None = None
    llm_models: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)
    stream: bool = True
