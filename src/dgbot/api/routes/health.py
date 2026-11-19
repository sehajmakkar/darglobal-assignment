"""Health endpoint used by Docker HEALTHCHECK, the hosting platform, and uptime checks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from dgbot import __version__
from dgbot.api.dependencies import get_app_settings
from dgbot.api.schemas import HealthResponse
from dgbot.core.config import Settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(settings: Annotated[Settings, Depends(get_app_settings)]) -> HealthResponse:
    return HealthResponse(version=__version__, env=settings.env)
