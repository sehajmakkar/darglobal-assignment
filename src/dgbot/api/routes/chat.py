"""POST /api/chat — streamed (Server-Sent Events) or plain JSON.

SSE event sequence: `sources` (numbered source cards, sent before the answer starts),
`token` (many), then `done` (final answer, cited sources, served model, latency) or `error`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from dgbot.api.dependencies import Runtime, get_rate_limiter, get_runtime
from dgbot.api.ratelimit import RateLimiter, client_ip
from dgbot.api.schemas import ChatRequest
from dgbot.chat.service import DoneEvent, ErrorEvent, SourcesEvent, TokenEvent
from dgbot.domain.chat import ChatAnswer

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    runtime: Annotated[Runtime, Depends(get_runtime)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> StreamingResponse | ChatAnswer:
    allowed, retry_after = limiter.check(client_ip(request))
    if not allowed:
        raise HTTPException(
            429,
            detail="Too many questions from this address — please wait a little and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    if not body.stream:
        result = await runtime.chat.answer(body.message, body.history)
        if isinstance(result, ErrorEvent):
            raise HTTPException(503 if result.code == "unavailable" else 429, detail=result.message)
        return result

    async def events() -> AsyncIterator[str]:
        async for event in runtime.chat.stream(body.message, body.history):
            if isinstance(event, SourcesEvent):
                yield _sse(
                    "sources",
                    {"lang": event.lang, "sources": [s.model_dump() for s in event.sources]},
                )
            elif isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, DoneEvent):
                yield _sse("done", event.answer.model_dump())
            elif isinstance(event, ErrorEvent):
                yield _sse("error", {"code": event.code, "message": event.message})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
