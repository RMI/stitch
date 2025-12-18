FROM python:3.13.1-slim-bookworm

WORKDIR /stitch

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

COPY pyproject.toml uv.lock /stitch/
RUN uv sync --frozen --no-install-workspace --package=stitch-core

COPY packages/stitch-core /stitch/packages/stitch-core

RUN uv sync --frozen --package=stitch-core

COPY deployments/db/seed_db.py .

CMD ["/stitch/.venv/bin/python", "/stitch/seed_db.py"]
