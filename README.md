# stitch

Stitch is a platform that integrates diverse oil & gas asset datasets, applies AI-driven enrichment with human review, and delivers curated, trustworthy data.

## Local Development

Local development is run via Docker Compose (DB + API + Frontend) with optional DB initialization/seeding.

The stack uses two compose files:

- **`docker-compose.yml`** — base services (API, DB, frontend, etc.)
- **`docker-compose.local.yml`** — local dev overrides (dev build target, debug logging, file-watch sync)

### Prerequisites

- Docker Desktop (includes Docker Engine + Docker Compose)

Verify:
```bash
docker --version
docker compose version
```

### Setup

Create your local environment file:
``` bash
cp env.example .env
```

Edit `.env` as needed (passwords, seed settings, etc.).

### Running the Application

Start (and build) the stack:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Or use `make dev-docker` (see [Make Targets](#make-targets)).

Or, if already built:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up db api frontend
```

Useful URLs:
- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Adminer (DB UI): http://localhost:8081

Note: The `db-init` service runs automatically (via `depends_on`) to apply schema and seed data based on `.env`:
- `STITCH_DB_SCHEMA_MODE`
- `STITCH_DB_SEED_MODE`
- `STITCH_DB_SEED_PROFILE`

## Reset (wipe DB volumes safely)

Stop containers and delete the Postgres volume (this removes all local DB data):
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v
```

Then start fresh:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up db api frontend
```

## Make Targets

Most common operations have `make` shortcuts. Run `make <target>` from the repo root.

### Build

| Target | Description |
|---|---|
| `make all` | Build all Python packages and the frontend |
| `make build-python` | Build all discovered Python packages (under `packages/`) |
| `make build-python PKG=stitch-auth` | Build a single package by name |
| `make frontend` | Build the frontend |

Python package discovery is automatic — any subdirectory of `packages/` with a `pyproject.toml` is included. Builds are incremental via stamp files under `build/`.

### Check / Lint / Test

| Target | Description |
|---|---|
| `make check` | Run all checks (lint, test, format-check, lock-check) |
| `make lint` | Run Python and frontend linters |
| `make test` | Run Python and frontend tests |
| `make format` | Auto-format Python and frontend code |
| `make format-check` | Check formatting without modifying files |
| `make lock-check` | Verify `uv.lock` is up to date |

### Docker

| Target | Description |
|---|---|
| `make dev-docker` | Start the full local-dev stack |
| `make prod-docker` | Start without local-dev overrides |
| `make docker-exec SVC=api` | Open a shell in a running container |
| `make docker-run SVC=api` | Spin up a one-off container with a shell |
| `make docker-logs SVC=api` | Tail logs for a service |
| `make docker-ps` | List running containers |
| `make stop-docker` | Stop containers (keep volumes) |
| `make clean-docker` | Stop containers and delete volumes |

`SVC` defaults to `api` if omitted.

### Clean

| Target | Description |
|---|---|
| `make clean` | Run all clean targets |
| `make clean-build` | Remove `build/` and `dist/` |
| `make clean-cache` | Remove `.ruff_cache` and `.pytest_cache` |
| `make clean-docker` | Stop containers and delete volumes |
| `make frontend-clean` | Remove frontend `dist/`, `node_modules`, and stamps |
