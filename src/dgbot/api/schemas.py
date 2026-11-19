"""HTTP request/response DTOs. Kept separate from domain models so the API can evolve
without leaking internals (and vice versa)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload. Phase 3+ adds index stats; Phase 4 adds remaining LLM quota."""

    status: Literal["ok"] = "ok"
    version: str
    env: str
