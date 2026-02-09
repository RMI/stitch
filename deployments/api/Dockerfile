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
    uv sync --frozen --no-install-workspace --package stitch-api

# ── dev target ────────────────────────────────────────────────────────
FROM base AS dev

COPY ./deployments/api /app/deployments/api
COPY ./packages /app/packages

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --package stitch-api

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── prod target ───────────────────────────────────────────────────────
FROM python:3.12-slim-trixie AS prod

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN groupadd --system --gid 999 stitch-app \
 && useradd --system --gid 999 --uid 999 --create-home stitch-app

COPY --from=dev --chown=stitch-app:stitch-app /app/.venv /app/.venv
COPY --from=dev --chown=stitch-app:stitch-app /app/deployments/api /app/deployments/api
COPY --from=dev --chown=stitch-app:stitch-app /app/packages/stitch-core /app/packages/stitch-core

ENV PATH="/app/.venv/bin:$PATH"
USER stitch-app

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
