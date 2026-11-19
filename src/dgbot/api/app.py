"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dgbot import __version__
from dgbot.api.dependencies import Runtime, build_runtime
from dgbot.api.ratelimit import RateLimiter
from dgbot.api.routes import chat, health
from dgbot.core.config import Settings, get_settings
from dgbot.core.errors import DgbotError
from dgbot.core.logging import configure_logging

logger = logging.getLogger(__name__)

RuntimeFactory = Callable[[Settings], Runtime]


def create_app(
    settings: Settings | None = None, runtime_factory: RuntimeFactory | None = None
) -> FastAPI:
    """Build the app. Tests pass `settings` and a `runtime_factory` with fakes."""
    settings = settings or get_settings()
    configure_logging(settings)
    factory = runtime_factory or build_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("dgbot %s starting (env=%s)", __version__, settings.env)
        try:
            app.state.runtime = factory(settings)
        except DgbotError as exc:  # still serve /api/health and the UI; chat returns 503
            logger.error("chat runtime not available: %s", exc)
            app.state.runtime, app.state.runtime_error = None, str(exc)
        yield
        if app.state.runtime is not None:
            app.state.runtime.close()
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
    app.state.runtime = None
    app.state.runtime_error = "starting up"
    app.state.rate_limiter = RateLimiter(
        settings.rate_limit_per_minute, settings.rate_limit_per_day
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    # Mounted last so /api/* routes win over static files.
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
