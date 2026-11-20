# Production image (Phase 6, D-051). Self-contained: UI, embedding models, search index and
# listings database are all built at image build time from files committed to the repo,
# so the container never downloads or builds anything at startup (D-006).
#
#   docker build -t dgbot .
#   docker run -p 7860:7860 --env-file .env dgbot
#
# Written for the classic builder too (no BuildKit-only syntax): Cloud Build's default
# `gcloud run deploy --source` builder doesn't enable BuildKit (C-009).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG NODE_IMAGE=node:20-bookworm-slim

# ── 1. Frontend: React build → static files ──────────────────────────────────
FROM ${NODE_IMAGE} AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── 2. Python dependencies (runtime groups only: no scraper, no dev tools) ───
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-default-groups --no-install-project --no-cache
COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-default-groups --no-editable --no-cache

# ── 3. Indexer: download models, build Qdrant index + listings.sqlite ────────
FROM builder AS indexer
ENV PATH="/app/.venv/bin:${PATH}" \
    DGBOT_EMBEDDING_CACHE_DIR=/opt/models \
    DGBOT_INDEX_DIR=/opt/index \
    DGBOT_PROCESSED_DATA_DIR=/app/data/processed \
    HF_HUB_DISABLE_PROGRESS_BARS=1
COPY data/processed ./data/processed
RUN python -m dgbot.ingestion \
    && rm -rf /opt/models/.locks

# ── 4. Runtime: slim, non-root, offline ──────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime
# UID 1000: the conventional non-root user (also what HF Spaces expects).
RUN useradd --create-home --uid 1000 app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=indexer --chown=app:app /opt/models /opt/models
# Qdrant local mode writes a lock file into the index directory → app must own it.
COPY --from=indexer --chown=app:app /opt/index /opt/index
COPY --from=indexer --chown=app:app /app/data/processed/manifest.json /app/data/processed/manifest.json
COPY --from=frontend --chown=app:app /build/dist /app/static
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DGBOT_ENV=prod \
    DGBOT_STATIC_DIR=/app/static \
    DGBOT_INDEX_DIR=/opt/index \
    DGBOT_EMBEDDING_CACHE_DIR=/opt/models \
    DGBOT_PROCESSED_DATA_DIR=/app/data/processed \
    HF_HUB_OFFLINE=1 \
    PORT=7860
USER app
WORKDIR /app
EXPOSE 7860
# Startup loads the embedding model (~1-5 s); give it room before health checks count.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '7860')}/api/health\", timeout=3)"]
CMD ["python", "-m", "dgbot.api"]
