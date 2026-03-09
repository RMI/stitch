# ── base: Python + uv + third-party deps ─────────────────────────────
FROM python:3.12-slim-trixie AS base

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1

COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

WORKDIR /app

# Third-party deps only — cached until uv.lock changes.
# All metadata via bind mounts (not copied into the layer).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --package stitch-seed

# ── runtime target ────────────────────────────────────────────────────
FROM base AS runtime

RUN groupadd --system --gid 999 stitch-app \
 && useradd --system --gid 999 --uid 999 --create-home stitch-app

COPY ./deployments /app/deployments
COPY ./packages /app/packages

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --package stitch-seed

ENV PATH="/app/.venv/bin:$PATH"
USER stitch-app

# Sensible defaults (override in compose/env as needed)
ENV API_BASE_URL="http://api:8000/api/v1" \
    POST_COUNT="5"

CMD ["python", "-m", "stitch.seed"]
