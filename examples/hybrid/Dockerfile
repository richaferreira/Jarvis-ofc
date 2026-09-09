# syntax=docker/dockerfile:1
# Em produção, fixe também os digests das imagens após validação no seu registro.
FROM ghcr.io/astral-sh/uv:0.10.0 AS uv
FROM python:3.11-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM python:3.11-slim-bookworm AS runtime
RUN useradd --uid 10001 --create-home jarvis
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=jarvis:jarvis hybrid ./hybrid
COPY --chown=jarvis:jarvis cypher ./cypher
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER jarvis
EXPOSE 8000
CMD ["uvicorn", "hybrid.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "8192", "--ws-max-queue", "16", "--limit-concurrency", "32", "--no-access-log"]
