# Stitch — Agent Guidance

Stitch integrates diverse oil & gas asset datasets, applies AI-driven enrichment with human
review, and delivers curated, trustworthy data. This file captures the things that aren't
obvious from reading one file.

Pointers: [`HACKING.md`](./HACKING.md) (setup & day-to-day workflow) ·
[`ARCHITECTURE.md`](./ARCHITECTURE.md) · [`CONTRIBUTING.md`](./CONTRIBUTING.md) ·
[`deployments/CI_DEPLOYMENTS.md`](./deployments/CI_DEPLOYMENTS.md) (deploy pipeline) ·
[`deployments/PERFORMANCE.md`](./deployments/PERFORMANCE.md) (query-layer performance).

## How to work here

- Read the surrounding code and conventions first; verify against the codebase rather than inferring.
- Make the smallest reversible change; touch only what the task requires.
- No speculative abstractions, architecture, or dependencies — a dependency is fine when
  justified (say why, and prefer the standard library or an existing one).
- Ambiguous or inconsistent? Stop and ask, or name the options, rather than guessing.
- Fix root causes; never weaken a test or mute an error to reach green.
- Show evidence (test output, the commands you ran) — don't just assert success.
- Architectural changes need discussion and maintainer sign-off _before_ a PR
  (`CONTRIBUTING.md`) — raise them rather than building them.

## Repository layout

Monorepo managed as a **uv workspace** (`[tool.uv.workspace]` in the root `pyproject.toml`),
plus one npm frontend. Python code uses the shared `stitch.*` namespace across every package.

- `packages/` — shared, versioned libraries. Dependency direction flows one way:
  `stitch-models` (generic `Source`/`Resource`/`SourceView` base types) → `stitch-ogsi`
  (the oil & gas domain model: `OGFieldSource`, `OGFieldResource`, source keys) →
  `stitch-client` (async HTTP client) and `stitch-auth` (JWT/Auth0 validation, permissions).
- `deployments/` — deployable apps, each a workspace member depending on `packages/`:
  `api` (the FastAPI service, `stitch-api`), `entity-linkage`, `stitch-llm`, `seed`,
  plus non-Python `db`, `stitch-frontend` (React + Vite), and `otel-collector`.

When you change a shared package, its consumers see it immediately (no reinstall) —
but run that package's tests _and_ its consumers' tests. See [`ARCHITECTURE.md`](./ARCHITECTURE.md)
for the high-level map.

## Common commands

Run from the repo root. The `Makefile` is the source of truth; a few high-value targets:

- `make check` — the pre-push gate: `lint` + `test` + `format-check` + `lock-check`. Run before pushing.
- `make lint` / `make test` / `make format` / `make format-check` / `make lock-check` — individual gates (Python via ruff, frontend via eslint/prettier/vitest).
- `make api-dev` / `make frontend-dev` / `make dev-docker` — the three dev entrypoints (see `HACKING.md` for which to pick).
- `make uv-sync-dev` — sync the whole workspace (`uv sync --group dev --all-packages`).
- `make clean` — remove build artifacts, caches, and dev docker volumes.

Single-package / single-test loops (the aggregate `make test` runs everything and is slow — see
`HACKING.md` for tight loops):

- `make api-test`, `make entity-linkage-test`, `make stitch-llm-test`, `make seed-test`, `make frontend-test`, `make pkg-test-<name>` — per-target suites.
- One file or test: `uv run --package <pkg> pytest <path>[::test_name] -x`, e.g.
  `uv run --package stitch-api pytest deployments/api/tests/db/test_query.py -x`.

Alembic migrations live in `deployments/api/alembic/`. Generate with `make alembic-autogenerate`,
check drift with `make alembic-check` (CI runs `check-alembic`).

## Architecture: the source → resource model

The core domain logic is spread across several files and only makes sense together. Read
these before touching query, coalescing, or permissions code:

- **Sources vs. resources.** Each dataset contributes typed _source_ records
  (`GemSource`, `WoodMacSource`, `RMISource`, `LLMSource` in `packages/stitch-ogsi/.../model/`).
  A _resource_ (`OGFieldResource`) is a curated field assembled from the sources linked to it.
  The four canonical source keys (`OGSISrcKey`) are `gem`, `wm`, `rmi`, `llm`.
- **Coalescing is per-request, not precomputed.** A resource's presented value for each field
  is chosen from its sources by priority. The in-memory coalescer is
  `deployments/api/src/stitch/api/coalesce.py`; its default order is
  `SRC_PRIORITY = (rmi, gem, wm, llm)`, overridable by the DB priority tables
  (`og_field_source_priority`, `og_field_resource_source_priority`). Query-side assembly
  lives in `deployments/api/src/stitch/api/db/queries.py`.
- **Licensing drives what a user sees.** A user's `licensed_sources` (set per request) filters
  which source values coalesce into a resource — which is _why_ coalescing can't be
  precomputed to one row per resource. Get the licensing/null-shell behavior right: read the
  existing query and permissions code rather than assuming, and confirm intent with the user
  before changing it. FK constraints guarantee no resource exists without a source and every
  user has at least one source permission, so don't add defensive null-handling for cases the
  schema forbids.
- The persistence model is EAV-style (see `deployments/api/src/stitch/api/db/model/`:
  `resource.py`, `membership.py`, `oil_gas_field_source*.py`, the `*_priority.py` tables) with
  a human-review flow via `merge_candidate.py`.

## Supporting services & deployment direction

`stitch-api` is the intended central broker / control plane — it owns auth, the domain model,
and the canonical data. `entity-linkage`, `stitch-llm`, and the ETL app are supporting
capabilities.
Note that the ETL processes are defined in a separate repo, but inherit interfaces that are defined here. the `seed` deployment provides a public approximation.

## Gotchas

- **Tests run on in-memory SQLite; production is Postgres.** DB code must be portable across
  both. In practice: prefer `Float` over `Numeric`, portable JSON columns, a refreshable
  regular TABLE over a Postgres materialized view, and portable winner-selection
  (`ROW_NUMBER()`). The API `conftest.py` skips creating tables marked
  `info={"is_view": True}` — anything that must exist in the SQLite test DB must not carry
  that marker.
- **The frontend is configured at runtime**, not at build time, via
  `deployments/stitch-frontend/public/config.json` (API/entity-linkage/LLM/ETL URLs, Auth0).
  CI injects these per deploy lane.

## CI gates that will fail a PR

- A **forbidden-patterns** scan (`.github/workflows/admin-forbidden-patterns.yml`) blocks
  lint/type escape-hatch comments and debug leftovers across the codebase — suppression
  comments for ruff, Pyright, Pylint, ESLint, and the TypeScript compiler, plus stray
  debug/trace statements left in JS or Python. Fix the root cause instead of suppressing;
  read the workflow for the exact pattern list. (This file describes the patterns rather than
  quoting them so it doesn't trip its own scan — the scan reads `.md` files too.)
- A **no-plan-file** check (`.github/workflows/admin-no-plan-file.yml`) fails if any
  `PLAN`-prefixed markdown file is tracked by git.

## Conventions

- **Keep changes minimal and focused**; one concern per PR (`CONTRIBUTING.md`).
- **Keep the public REST API as stable as possible.** If an internal refactor would change endpoints or
  query params, map internally instead of changing the public surface.
- Plans, specs, and reviews are kept under `.agents/docs/` — scratch only; never `git add`
  them. (Locally excluded via `.git/info/exclude`, not a committed `.gitignore` rule, so the
  ignore isn't guaranteed in a fresh clone.)
- Git: don't commit or push unless asked; never rewrite history or force-push. **Merge commits
  only** — no squash, no rebase merges (`CONTRIBUTING.md`). Conventional Commit messages; link
  JIRA issues as `STIT-#<number>` in PR titles.
