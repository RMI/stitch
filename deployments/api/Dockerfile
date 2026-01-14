FROM python:3.14.2-slim

# better console streaming for docker logs
ENV PYTHONUNBUFFERED=1
WORKDIR /repo


# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/repo/.venv/bin:$PATH"

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy


# --- Copy workspace metadata first (better caching)
COPY pyproject.toml uv.lock ./

# # Copy the member pyprojects (and/or whole packages) that are needed to resolve deps
# COPY deployments/api/pyproject.toml deployments/api/pyproject.toml
# COPY packages/stitch-core/pyproject.toml packages/stitch-core/pyproject.toml
# COPY packages/stitch-core/pyproject.toml packages/stitch-core/pyproject.toml
# COPY dev/stitch-cli/pyproject.toml dev/stitch-cli/pyproject.toml

# # If uv needs source trees to build/editable install, copy them too:
# COPY packages/stitch-core packages/stitch-core
# COPY dev/stitch-cli dev/stitch-cli

COPY . .

# Install deps for the api project (important: target the subproject)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --project deployments/api --no-install-workspace

# Now copy api source last
COPY deployments/api/src deployments/api/src

ENV PYTHONPATH=/repo/deployments/api

CMD ["fastapi", "run", "deployments/api/src/stitch/api/main.py"]
