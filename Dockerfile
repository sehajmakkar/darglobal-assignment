# Phase 0b walking skeleton (D-017). Later phases add a frontend build stage and an
# index-build step; the runtime stage stays slim and never contains scraper deps (D-022).
# Written for the classic builder too (no BuildKit-only syntax): Cloud Build's default
# `gcloud run deploy --source` builder doesn't enable BuildKit (C-009).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ── 1. Builder: resolve the locked runtime deps into a venv ──────────────────
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Dependencies first (cached layer), project code second.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-cache

# ── 2. Runtime: just Python + the venv, as a non-root user ───────────────────
FROM ${PYTHON_IMAGE} AS runtime
# UID 1000 matches what Hugging Face Spaces runs containers as.
RUN useradd --create-home --uid 1000 app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DGBOT_ENV=prod \
    PORT=7860
USER app
WORKDIR /home/app
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '7860')}/api/health\", timeout=3)"]
CMD ["python", "-m", "dgbot.api"]
