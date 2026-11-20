"""Health endpoint used by Docker HEALTHCHECK, the hosting platform, and uptime checks.

Always 200 while the process is up (liveness); `ready` says whether chat can answer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from dgbot import __version__
from dgbot.api.dependencies import get_app_settings
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
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> HealthResponse:
    runtime = request.app.state.runtime
    return HealthResponse(
        version=__version__,
        env=settings.env,
        ready=runtime is not None,
        detail=None if runtime else request.app.state.runtime_error,
        index={k: runtime.index_info.get(k) for k in _INDEX_FIELDS} if runtime else None,
        llm_models=list(settings.llm_models),
    )
