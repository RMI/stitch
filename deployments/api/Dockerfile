# ── base: Python + uv + third-party deps ─────────────────────────────
FROM python:3.12-slim-trixie AS base

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1

COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

# --- Copy workspace metadata
COPY pyproject.toml README.md uv.lock ./

COPY deployments/api/pyproject.toml deployments/api/pyproject.toml
COPY packages/stitch-core/pyproject.toml packages/stitch-core/pyproject.toml
COPY packages/stitch-auth/pyproject.toml packages/stitch-auth/pyproject.toml
#
# 3rd party deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --project deployments/api --no-install-workspace

# Install deps for the api project (important: target the subproject)
# Create a venv we will populate with WHEEL installs (not editable)
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the member pyprojects (and/or whole packages) that are needed to resolve deps
COPY packages/stitch-auth/src packages/stitch-auth/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --wheel --out-dir /app/dist packages/stitch-auth

COPY packages/stitch-core/README.md packages/stitch-core/README.md
COPY packages/stitch-core/src packages/stitch-core/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --wheel --out-dir /app/dist packages/stitch-core

COPY deployments/api/README.md deployments/api/README.md
COPY deployments/api/src deployments/api/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --wheel --out-dir /app/dist deployments/api

# Install the built wheels into the venv (non-editable, self-contained)
RUN python -m pip install --no-cache-dir /app/dist/*.whl

# ── runtime target ────────────────────────────────────────────────────
FROM base AS runtime

RUN groupadd --system --gid 999 stitch-app \
 && useradd --system --gid 999 --uid 999 --create-home stitch-app

COPY ./deployments/api /app/deployments/api
COPY ./packages /app/packages

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --package stitch-api

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
