FROM python:3.14.2-slim AS builder

# better console streaming for docker logs
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /repo

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

# --- Copy workspace metadata
COPY pyproject.toml uv.lock ./

# Copy the member pyprojects (and/or whole packages) that are needed to resolve deps
COPY deployments/api/pyproject.toml deployments/api/pyproject.toml
COPY dev/stitch-cli/pyproject.toml dev/stitch-cli/pyproject.toml
COPY packages/schema/pyproject.toml packages/schema/pyproject.toml
COPY packages/stitch-core/pyproject.toml packages/stitch-core/pyproject.toml

# If uv needs source trees to build/editable install, copy them too:
COPY deployments deployments
COPY dev/stitch-cli dev/stitch-cli
COPY packages/schema packages/schema
COPY packages/stitch-core packages/stitch-core

# Install deps for the api project (important: target the subproject)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --project deployments/api --no-install-workspace

# Now copy api source last
COPY deployments/api/src deployments/api/src

ENV PYTHONPATH=/repo/deployments/api

# -------------------------------------------------------

FROM python:3.14.2-slim AS runtime

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy the ready-to-run virtualenv
COPY --from=builder /repo/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy only the API source (runtime code)
COPY deployments/api/src /app/src
ENV PYTHONPATH=/app/src

CMD ["fastapi", "run", "stitch/api/main.py"]
