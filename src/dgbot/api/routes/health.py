"""Health endpoint used by Docker HEALTHCHECK, the hosting platform, and uptime checks.

Always 200 while the process is up (liveness); `ready` says whether chat can answer.
`?wait=N` holds the request until the search model has loaded (warm-up pings, the UI).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from dgbot import __version__
from dgbot.api.dependencies import get_app_settings, wait_for_runtime
from dgbot.api.schemas import HealthResponse
from dgbot.core.config import Settings

router = APIRouter(prefix="/api", tags=["health"])
_INDEX_FIELDS = (
    "embedding_model",
    "chunks",
    "chunks_by_type",
    "listings_rows",
    "snapshot_fingerprint",
    "built_at",
    "data_fetched",
)


@router.get("/health")
async def health(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    wait: Annotated[
        float, Query(ge=0, le=280, description="seconds to wait while the model loads")
    ] = 0,
) -> HealthResponse:
    runtime = await wait_for_runtime(request, wait)
    return HealthResponse(
        version=__version__,
        env=settings.env,
        ready=runtime is not None,
        warming_up=not request.app.state.runtime_loaded.is_set(),
        detail=None if runtime else request.app.state.runtime_error,
        index={k: runtime.index_info.get(k) for k in _INDEX_FIELDS} if runtime else None,
        llm_models=list(settings.llm_models),
    )
