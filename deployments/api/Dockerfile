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
COPY pyproject.toml uv.lock ./

# Copy the member pyprojects (and/or whole packages) that are needed to resolve deps
COPY deployments/api/pyproject.toml deployments/api/pyproject.toml
COPY deployments/api/src /app/src

COPY packages/stitch-core/pyproject.toml packages/stitch-core/pyproject.toml
COPY packages/stitch-core/src packages/stitch-core/src

COPY dev/stitch-cli/pyproject.toml dev/stitch-cli/pyproject.toml
COPY dev/stitch-cli/src dev/stitch-cli/src

COPY packages/schema/pyproject.toml packages/schema/pyproject.toml
COPY packages/schema/src packages/schema/src

# Install deps for the api project (important: target the subproject)
# Create venv and sync using the lock for the API project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --project deployments/api --no-install-workspace

# -------------------------------------------------------

FROM python:3.12.12-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy the ready-to-run virtualenv
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy only the API source (runtime code)
COPY deployments/api/src /app/src
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "stitch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
