FROM python:3.12.12-slim-trixie AS builder

# better console streaming for docker logs
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
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

# -------------------------------------------------------

FROM python:3.12.12-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy the ready-to-run virtualenv
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
