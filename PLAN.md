# Extract `stitch-observability` package and wire it into API, entity-linkage, and stitch-llm

## Context

OpenTelemetry tracing currently lives only inside the API, in
`deployments/api/src/stitch/api/observability/tracing.py`. [PR #149](https://github.com/RMI/stitch/pull/149)
already extracted this into a shared `stitch-observability` package and wired the
other services onto it — but it is based on `feat/stitch-service`, which carries
30 commits of the **job-framework refactor** (`stitch-jobs` + `stitch-service`)
that we are *not* pursuing right now. On `main`, those package directories exist
on disk only as leftover `.pyc` files; there is no real `create_app` factory.

This plan captures the *spirit* of PR #149 — a reusable tracing package plus
end-to-end instrumentation of the three services — but rebased onto `main`,
wiring each service **directly** (plain `FastAPI(...)`) instead of through the
`stitch-service` factory. It touches only: the new package, the API shim, EL,
stitch-llm, and workspace/Makefile config. It deliberately does **not** touch
`stitch-jobs` / `stitch-service`.

Outcome: one source of truth for tracing setup + export; EL and stitch-llm emit
spans and propagate the W3C `traceparent` on their httpx calls, so a request
flows as a single linked trace (frontend → EL/LLM → API → DB) into the existing
collector → Jaeger sidecars, with zero compose changes.

## Reference implementation

PR #149's package is the template and can be ported almost verbatim (it does not
depend on the job framework):
`git show feat/observability-package:packages/stitch-observability/...`

## Changes

### 1. New package `packages/stitch-observability` (`stitch.observability`)

Port these files verbatim from `feat/observability-package`:

- `src/stitch/observability/__init__.py` — re-exports `OTelSettings`,
  `configure_tracing`, `get_tracer`, `instrument_fastapi`, `instrument_httpx`,
  `instrument_sqlalchemy`, `shutdown_tracing`, `LoggingSpanExporter`.
- `src/stitch/observability/settings.py` — `OTelSettings` pydantic mixin reading
  the standard `OTEL_*` env vars (`otel_enabled`, `otel_traces_exporter`,
  `otel_exporter_otlp_endpoint`, `otel_sample_ratio` bounded `[0,1]`).
- `src/stitch/observability/tracing.py` — keyword-only `configure_tracing(*, service_name, ...)`,
  the `LoggingSpanExporter`, `shutdown_tracing`, `get_tracer`, and the three
  `instrument_*` helpers. **Instrumentor imports stay lazy** (inside each
  `instrument_*` fn) — the FastAPI/httpx/SQLAlchemy instrumentation packages list
  the instrumented lib as an optional "instruments" extra, and a top-level import
  breaks `*-test-exact` for services that lack that lib.
  Incorporates deferred nits #2 and #3 below.
- `pyproject.toml` — deps: `opentelemetry-sdk`, `-exporter-otlp-proto-grpc`,
  `-instrumentation-fastapi`, `-instrumentation-httpx`, `-instrumentation-sqlalchemy`,
  `pydantic-settings`; `module-name = "stitch.observability"`.
- `tests/test_tracing.py` — port verbatim (provider construction, disabled→None,
  LoggingSpanExporter one-record-per-span, OTelSettings bounds), plus a new case
  asserting a >2000-char attribute value is truncated (nit #2).
- `README.md` — port.

### 2. API — make `tracing.py` a thin shim (behavior-preserving)

Replace `deployments/api/src/stitch/api/observability/tracing.py` body with the
PR #149 shim: it keeps the historical surface (`SERVICE_NAME = "stitch-api"`,
`configure_tracing(settings)`, `instrument_fastapi`, `instrument_sqlalchemy`,
`LoggingSpanExporter`) by delegating to `stitch.observability`, so `main.py:42`
(`configure_tracing(settings)`) and `db/config.py:63` (`instrument_sqlalchemy`)
are unchanged. The API keeps FastAPI + SQLAlchemy instrumentation only (it is the
DB-backed leaf; no httpx instrumentation, matching today). The API's
query-timing / request-logging / sinks layer stays API-specific and untouched.
`observability/__init__.py` re-exports are unchanged. Add
`stitch-observability` to `deployments/api/pyproject.toml` deps + `[tool.uv.sources]`.

### 3. entity-linkage — wire tracing directly into the plain app

- `settings.py`: `class Settings(OTelSettings)` (import from `stitch.observability`,
  drop the now-unused `BaseSettings` import). Its own `model_config` /
  `populate_by_name` are kept.
- `main.py`: mirror the API's `main.py` pattern (no `create_app`) —
  ```python
  from stitch.observability import (
      configure_tracing, instrument_fastapi, instrument_httpx, shutdown_tracing,
  )
  settings = get_settings()
  _tracer_provider = configure_tracing(
      service_name="stitch-entity-linkage",
      enabled=settings.otel_enabled,
      exporter=settings.otel_traces_exporter,
      otlp_endpoint=settings.otel_exporter_otlp_endpoint,
      sample_ratio=settings.otel_sample_ratio,
  )
  ```
  Call `shutdown_tracing(_tracer_provider)` at the end of `lifespan`; after
  `register_middlewares`, guard `if _tracer_provider is not None:` then
  `instrument_fastapi(app)` + `instrument_httpx()`. `instrument_httpx()` is what
  propagates `traceparent` on the downstream `stitch-client` calls. No SQLAlchemy
  (EL has none). Define `_tracer_provider` above `lifespan` to avoid a NameError
  if a later import fails between assignment and app creation.
- `conftest.py` (new, rootdir): `os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")`
  before app import (mirrors the API's rootdir conftest).
- `pyproject.toml`: add `stitch-observability` to deps + `[tool.uv.sources]`.

### 4. stitch-llm — identical treatment

Same as EL: `Settings(OTelSettings)`, direct wiring in `main.py` with
`service_name="stitch-llm"`, `instrument_fastapi` + `instrument_httpx` (httpx
covers both the Azure OpenAI client and the downstream `stitch-client`), new
rootdir `conftest.py`, and pyproject dep + source.

### 5. Workspace + Makefile

- Root `pyproject.toml`: add `"packages/stitch-observability"` to
  `[tool.uv.workspace].members` and `stitch-observability = { workspace = true }`
  to `[tool.uv.sources]`.
- `Makefile`: add `pkg-build-observability` / `pkg-test-observability` /
  `pkg-test-exact-observability` targets and append them to the aggregate
  `pkg-build` / `pkg-test` / `pkg-test-exact` targets and the `.PHONY` list
  (port the PR #149 Makefile diff).
- `uv.lock`: regenerated by `uv sync` / `uv lock`.

## Deferred OTel review nits (folded in — all)

From the `otel-pr-142` review backlog; this work relocates the affected code, so
they land here:

1. **NameError guard.** In each `main.py` that reads `_tracer_provider` inside
   `lifespan`, declare `_tracer_provider = None` *above* the `lifespan` def so a
   failed import between assignment and app creation can't NameError. Apply to
   the API `main.py` and the new EL / stitch-llm wiring.
2. **Truncate LoggingSpanExporter attributes.** `dict(span.attributes)` dumps the
   full bag — incl. SQLAlchemy `db.statement` — untruncated to stdout / Log
   Analytics. Add a max-length pass (2000-char cap, `[:max] + "…"`) over each
   attribute value in the package's `LoggingSpanExporter.export`, mirroring
   `query_timing._normalize_statement`
   (`deployments/api/src/stitch/api/observability/query_timing.py:32`).
3. **SimpleSpanProcessor tradeoff comment.** Keep `SimpleSpanProcessor` for the
   `console` path (immediate dev visibility; otlp already batches) but add a
   comment noting it exports synchronously on the request thread and could move
   to `BatchSpanProcessor` if hot-path cost matters.
4. **`get_engine` lru_cache comment.** In
   `deployments/api/src/stitch/api/db/config.py` (~line 62, at the
   `instrument_sqlalchemy` call), add a one-line comment that `get_engine` is
   `@lru_cache`'d so the SQLAlchemy instrumentation runs once per process.
5. **Test isolation in the API `tests/observability/test_tracing.py`.**
   (a) `test_console_exporter_returns_provider` mutates the process-global
   provider via `set_tracer_provider`; monkeypatch
   `stitch.observability.tracing.trace.set_tracer_provider` to a no-op (note: the
   target module is now the *package*, since the API `configure_tracing` delegates
   there through the shim) instead of relying on the "benign global mutation"
   comment. (b) Replace the `"INTERNAL"` / `"UNSET"` string literals in
   `TestLoggingSpanExporter` with `SpanKind.INTERNAL.name` / `StatusCode.UNSET.name`.

## Out of scope (the job-framework direction)

No changes to `packages/stitch-jobs` or `packages/stitch-service`, and no
`create_app`. The `job.run` span-with-Link work from PR #149 lives in
`stitch-jobs` and is intentionally omitted.

## Verification

1. `make pkg-test-observability` — package unit tests pass.
2. `make api-test`, EL tests, LLM tests — each service's suite passes with
   tracing disabled via its rootdir `conftest.py`.
3. `make lint` / forbidden-patterns CI — no `noqa`/`type:ignore`/etc.
4. End-to-end (optional, needs sidecars): bring up the stack with the otel
   sidecars (`make reboot-docker-heavy` + `full`/`friends` profile so EL + LLM
   run), trigger an EL run and an LLM suggestion from the frontend, and confirm
   in Jaeger (http://localhost:16686) that `stitch-entity-linkage` /
   `stitch-llm` spans appear and share a `trace_id` with the downstream
   `stitch-api` spans (traceparent propagation via `instrument_httpx`). No
   compose edits needed — EL/LLM already load the shared `.env`
   (`OTEL_TRACES_EXPORTER=otlp`, collector endpoint).
