"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dgbot import __version__
from dgbot.api.routes import health
from dgbot.core.config import Settings, get_settings
from dgbot.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Pass `settings` in tests; production reads them from the env."""
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Long-lived resources (embedder, vector store, LLM client) get created here
        # in later phases and closed on shutdown.
        logger.info("dgbot %s starting (env=%s)", __version__, settings.env)
        yield
        logger.info("dgbot shutting down")

    app = FastAPI(
        title=settings.app_title,
        version=__version__,
        lifespan=lifespan,
        # Interactive docs are handy for reviewers; they expose nothing secret.
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(health.router)
    # Mounted last so /api/* routes win over static files.
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
