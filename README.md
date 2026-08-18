# Stitch

Stitch is an oil & gas asset data platform built by [RMI](https://rmi.org). It consolidates fragmented upstream datasets into a single, provenance-aware view of oil & gas fields, backed by a database and exposed through a UI and API. It's built for climate researchers, energy analysts, and policy teams who need trustworthy, source-attributed data.

**What Stitch does:**

- **Consolidates** oil & gas asset data from multiple upstream sources into a unified schema
- **Enriches** records with AI-driven inference where source data is incomplete
- **Reviews** merges and enrichments through a human-in-the-loop workflow
- **Serves** curated, source-attributed data through a UI and API, with permission-aware access by source

**See it live:**

- Dress rehearsal (prod-ish): https://brave-cliff-09493391e.7.azurestaticapps.net/
- Dev (`main`): https://witty-mushroom-017a3dc1e.1.azurestaticapps.net/

## Local Development

For the full development guide, see [HACKING.md](./HACKING.md).

Quick start:

```bash
cp env.example .env
make dev-docker
```

Useful URLs:

- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Adminer (DB UI): http://localhost:8081

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

## Documentation

- [HACKING.md](./HACKING.md) — day-to-day development workflow
- [CONTRIBUTING.md](./CONTRIBUTING.md) — how to open issues and pull requests
- [ARCHITECTURE.md](./ARCHITECTURE.md) — monorepo layout and structure
- [AGENTS.md](./AGENTS.md) — instructions for AI coding agents working in this repo
