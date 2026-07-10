# Hacking on Stitch

This guide covers the day-to-day development workflow in the Stitch monorepo.

## Monorepo layout

* `deployments/api` — FastAPI service (`stitch-api`)
* `deployments/stitch-frontend` — React + Vite frontend
* `deployments/db` — database bootstrap and role scripts
* `deployments/loadtest` — k6 load test + seeder, and the Grafana dashboards
* `packages/` — shared Python packages

## Prerequisites

* Docker Desktop (`docker`, `docker compose`)
* `uv` for Python dependency and workspace management
* Node.js + npm for frontend development

## First-time setup

From the repo root:

```bash
cp env.example .env
make uv-sync-dev
```

You can also run the equivalent `uv` command directly:

```bash
uv sync --group dev --all-packages
```

## The main entrypoints

In most cases, start with one of these three commands:

* `make frontend-dev`
* `make api-dev`
* `make dev-docker` (or `make reboot-docker`)

### `make frontend-dev`

Use this when you are primarily working on the frontend.

This target:

* installs frontend dependencies if needed
* starts the supporting local services in Docker
* runs the Vite dev server on the host

The API and supporting services run in Docker, while the frontend runs locally with fast rebuilds.

```bash
make frontend-dev
```

### `make api-dev`

Use this when you are primarily working on the API.

This target:

* starts the supporting local services in Docker
* runs the FastAPI app on the host with reload enabled

The frontend and supporting services run in Docker, while the API runs locally for a tighter backend loop.

```bash
make api-dev
```

### `make dev-docker`

Use this when you want the whole local stack running in Docker.

This is the best choice when you want the most production-like local setup or do not need to run either app directly on the host.

```bash
make dev-docker
```

## Which one should I use?

A simple rule of thumb:

* changing React/UI code: `make frontend-dev`
* changing FastAPI/backend code: `make api-dev`
* validating the whole stack together: `make dev-docker`

## Useful local URLs

Depending on which entrypoint you use, these are the main local endpoints:

* Frontend: `http://localhost:3000`
* API docs: `http://localhost:8000/docs`
* Adminer: `http://localhost:8081`

## Other useful targets

You do not need to memorize the whole Makefile, but these are worth knowing.

### `make check`

Runs the main verification suite in one command:

* lint
* tests
* format checks
* lockfile checks

Use this before pushing or when you want a quick confidence pass.

```bash
make check
```

### `make clean`

Resets local build artifacts, caches, frontend install/build outputs, and Docker state.

⚠️ **Warning:** this target includes `clean-docker`, which removes Docker containers **and volumes**. This will delete your local database data.

Use this when you want a completely fresh environment.

```bash
make clean
```

### `make reboot-docker`

Performs a clean Docker reset and immediately brings the full stack back up with builds.

This is a convenience target for the common “wipe it and restart everything” workflow.

```bash
make reboot-docker
```

### `make follow-stack-logs`

Follows logs for the full Docker-based local stack.

Useful when debugging service startup or cross-service interactions.

```bash
make follow-stack-logs
```

## Common quality commands

From the repo root:

```bash
make lint
make test
make format
make format-check
make lock-check
make check
```

## When things get weird

A good escalation path is:

```bash
make check
make clean
make reboot-docker
```

That sequence catches most local issues caused by stale caches, stale frontend installs, or stale Docker volumes.
