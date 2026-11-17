# syntax=docker/dockerfile:1

# ---- build: install dependencies with uv into a virtual environment ----------------------------
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# ---- runtime: small image, non-root user ------------------------------------------------------
FROM python:3.13-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# Apply migrations, then serve the dashboard. Override the command to run the worker instead.
CMD ["sh", "-c", "alembic upgrade head && pricewatch serve --host 0.0.0.0 --port ${PORT:-8000}"]
