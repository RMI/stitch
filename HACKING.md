# Hacking on Stitch

This guide covers day-to-day development in the current Stitch monorepo.

## Monorepo layout

- `packages/stitch-core`: shared core domain logic
- `packages/stitch-auth`: auth/claims/validation package
- `deployments/api`: FastAPI service (`stitch-api`)
- `deployments/stitch-frontend`: React + Vite frontend
- `deployments/db`: DB bootstrap/role scripts

## Prerequisites

- Docker Desktop (`docker`, `docker compose`)
- `uv` for Python dependency/workspace management
- Node.js + npm (for frontend-only workflows)

## First-time setup

```bash
cp env.example .env
uv sync --group dev --all-packages
```

If you are running the full stack via Docker, `uv sync` is optional unless you also run tests/tools on host.

## Run the stack (recommended)

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Or:

```bash
make dev-docker
```

Useful local URLs:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Adminer: http://localhost:8081

## Common dev commands

Run from repo root.

```bash
make lint
make test
make format
make format-check
make check
```

Python-only:

```bash
uv run ruff check
uv run ruff format
uv run pytest packages/stitch-core
uv run pytest deployments/api
```

Frontend-only:

```bash
npm --prefix deployments/stitch-frontend ci
npm --prefix deployments/stitch-frontend run dev
npm --prefix deployments/stitch-frontend run lint
npm --prefix deployments/stitch-frontend run test:run
```

## Working in containers

Start stack, then use Docker Compose helpers as needed:

```bash
make docker-ps
make docker-logs SVC=api
make docker-exec SVC=api
make docker-run SVC=api
```

## Reset local DB data

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v
docker compose -f docker-compose.yml -f docker-compose.local.yml up db api frontend
```

Or:

```bash
make clean-docker
make dev-docker
```

## Contribution expectations

- Keep changes scoped to the relevant package/deployment.
- Add or update tests with behavior changes.
- Run `make check` before opening a PR.
- Prefer small, reviewable commits.
