# ── shared base: Python + uv ──────────────────────────────────────────
FROM python:3.12.12-slim-trixie AS base-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY deployments/api/pyproject.toml deployments/api/pyproject.toml

# -- base installs 3rd part deps only
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --package stitch-api

# ── dev target: sync editable, we'll use `develop` in docker compose to watch/rebuild
FROM base-uv AS dev

COPY ./deployments/api /app/deployments/api
COPY ./packages /app/packages

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --package stitch-api


ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── builder: full source → wheel + sdist ──────────────────────────────
FROM base-uv AS builder

COPY pyproject.toml uv.lock ./
COPY packages/stitch-core packages/stitch-core
COPY deployments/api deployments/api

RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --package stitch-api --out-dir /app/dist

# ── prod target: clean image with only the installed wheel ────────────
FROM python:3.12.12-slim-trixie AS prod

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN useradd -m -u 1000 appuser

COPY --from=builder /app/dist /tmp/dist
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir --find-links /tmp/dist stitch-api && \
    rm -rf /tmp/dist

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
