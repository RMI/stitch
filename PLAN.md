# Fix: auth/resources fail to load — CORS preflight crash in OTel instrumentation

## Context

Resources fail to load and the colophon diagnostics show `Auth Claims Status: Unavailable` /
`Auth Claims Error: Failed to fetch`, both locally (`make reboot-docker`, main) and on PR
previews. This is **not** an auth problem — the PR backend even reports `Auth Disabled: true`
and still fails.

The real cause is a two-version incompatibility that crashes **CORS preflight requests**:

1. **FastAPI ≥ 0.137** (lock pins `0.139.2`, bumped in PR #177) changed `include_router` so
   `app.routes` now holds lazy `_IncludedRouter` nodes that have **no `.path` attribute**
   (it no longer flattens child routes). `make reboot-docker` builds from `uv.lock`, so both
   Docker-local and PR run this version.
2. **`opentelemetry-instrumentation-fastapi 0.63b1`** reads `starlette_route.path` on a
   `Match.PARTIAL` route **without a guard** (`_get_route_details`, line 495). A browser CORS
   preflight `OPTIONS` yields exactly a partial match (path matches `/auth/me`, method
   `OPTIONS` ≠ `GET`) → `AttributeError: '_IncludedRouter' object has no attribute 'path'` —
   the repeating 500s in the backend log.
3. **Middleware ordering** turns that 500 into `Failed to fetch`: `instrument_fastapi(app)`
   runs *after* `register_middlewares(...)`, so the OTel ASGI middleware wraps **outside**
   `CORSMiddleware`. The preflight crashes in OTel before CORS runs, so the error response
   has **no `Access-Control-Allow-Origin`** header → the browser blocks it → `Failed to fetch`.

This explains the observed split: `/health/details` works (plain GET, no `Authorization`
header → **no preflight**); `/auth/me` fails (`Authorization: Bearer` header → **triggers a
preflight**).

**Why CI stayed green on the dependabot fastapi bump:** the rootdir `conftest.py` sets
`OTEL_TRACES_EXPORTER=none` *before* the app is imported, so the shared test `app` is built
with `_tracer_provider is None` and is **never instrumented** — the OTel ASGI middleware (the
thing that crashes) is absent from the stack in every existing test, including the existing
preflight test in `tests/test_middleware.py`. No test exercises a preflight through an
*instrumented* app.

Upstream: fixed in [otel-contrib PR #4700](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4700)
(merged 2026-06-22), first released in **0.64b0**; latest **0.65b0** (2026-07-16). All
`opentelemetry-instrumentation-*` packages ship only as `0.NbM` betas — that is their normal
release channel (the app already runs `0.63b1`), so `0.65b0` is a like-for-like published release.

**Success criterion:** After `make reboot-docker`, a preflight `OPTIONS /api/v1/auth/me` returns
2xx with CORS headers, the colophon panel shows populated Auth Claims (no `Failed to fetch`), the
backend log no longer emits the `_IncludedRouter` `AttributeError`, and the new regression tests
pass (and demonstrably fail against the pre-fix dependency).

## Approach

Order of work: (1) extract the app factory, (2) add regression tests and confirm they reproduce
the crash against the current dependency, (3) upgrade the dependency, (4) confirm green.

### Step 1 — Extract a `create_app()` factory (enables testing + bakes in the correct order)

`deployments/api/src/stitch/api/main.py`: move the assembly currently at lines 44–51 into a
factory, so tests can build an *instrumented* app in the real production order. Instrument
**before** `register_middlewares(...)` — because Starlette's `add_middleware` prepends
(last-added = outermost), this yields the correct outer→inner order
`RequestTimingMiddleware → CORSMiddleware → OTel → router`: `RequestTimingMiddleware` stays
outermost (preserving the intent noted in `middleware.py:31-33`), and **`CORSMiddleware` now
sits outside OTel** (Fix for symptom #3 above).

```python
def create_app(settings: Settings, *, tracer_provider) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    # Instrument first so OTel is inner and CORS ends up outside it; RequestTimingMiddleware
    # (added last inside register_middlewares) remains the outermost layer.
    if tracer_provider is not None:
        instrument_fastapi(app)
    register_middlewares(application=app, settings=settings)
    app.include_router(base_router)
    return app
```

Module level keeps the existing globals and singleton, just delegating assembly:

```python
settings = get_settings()
configure_logging(level=settings.log_level, log_format=settings.log_format)
_tracer_provider = configure_tracing(settings)
app = create_app(settings, tracer_provider=_tracer_provider)
```

Keep `base_router` construction (lines 19–23), `lifespan` (which still references the module
global `_tracer_provider`), and the `OperationalError` exception handler exactly as they are.
No change to `middleware.py`.

### Step 2 — Add regression tests

New file `deployments/api/tests/observability/test_instrumented_app.py`, matching existing
async style (`@pytest.mark.anyio`, httpx `AsyncClient` over `ASGITransport` — **no lifespan**,
as in `integration_client`). Both tests build the app via `create_app(...)` with instrumentation
**enabled** (pass a real `opentelemetry.sdk.trace.TracerProvider()` so the gate passes and
`FastAPIInstrumentor.instrument_app` installs the ASGI middleware). Auth/DB deps are overridden
via `app.dependency_overrides` exactly as `tests/conftest.py` does (`get_token_claims`,
`get_current_user`, `get_uow`). Origin to send is `http://localhost:3000` (the `Settings`
default under the dotenv-isolated test env; `.rstrip("/")`-ed, no trailing slash).

- **Test A — isolates the OTel/`_IncludedRouter` crash (dependency regression):**
  Send a **bare** `OPTIONS /api/v1/auth/me` (no `Access-Control-Request-Method` header, so
  `CORSMiddleware` does *not* short-circuit it — it reaches OTel regardless of middleware
  order). Assert the response is **405** (method-not-allowed), i.e. **not** a 500. Against the
  current `opentelemetry-instrumentation-fastapi 0.63b1` + `fastapi 0.139.2` this returns a 500
  (`AttributeError: '_IncludedRouter' object has no attribute 'path'`); after the upgrade it
  returns 405. This is the test that would have caught the dependabot bump.

- **Test B — end-to-end CORS preflight (user-facing symptom):**
  Send a proper preflight: `OPTIONS /api/v1/auth/me` with `Origin: http://localhost:3000`,
  `Access-Control-Request-Method: GET`, `Access-Control-Request-Headers: authorization`.
  Assert status is 2xx **and** the `access-control-allow-origin` header is present. Reproduces
  exactly what the browser does and asserts the response is CORS-visible.

Note: these must run under the **`--exact`** test target (see verification) so the environment
matches `uv.lock` (fastapi 0.139.2). The non-exact `make api-test` target uses the host `.venv`
(currently fastapi 0.136.1, which flattens routers) and would not reproduce the crash.

### Step 3 — Upgrade the OTel instrumentation group (root-cause fix)

`deployments/api/pyproject.toml` (lines 15–16): raise the floors past the fix.

```
"opentelemetry-instrumentation-fastapi>=0.65b0",
"opentelemetry-instrumentation-sqlalchemy>=0.65b0",
```

Then re-lock so the whole OTel group (and the matching `opentelemetry-api`/`-sdk` 1.44.x it
requires) resolves together:

```
uv lock --upgrade-package opentelemetry-instrumentation-fastapi \
        --upgrade-package opentelemetry-instrumentation-sqlalchemy
```

- The `>=…b0` specifier already permits pre-release tags (as `>=0.51b0` does today).
- Leave `opentelemetry-sdk` / `-exporter-otlp-proto-grpc` floors (lines 13–14) as-is; uv pulls
  compatible 1.44.x during the re-lock.
- Lockfile is the workspace root `/Users/aaxthelm/Documents/SPD/stitch/uv.lock` (verify
  `uv lock --check` passes / `python-lock-check` workflow stays green).

## Critical files

- `deployments/api/src/stitch/api/main.py` — extract `create_app()`; instrument before
  `register_middlewares` (Fix #3); module-level `app = create_app(...)`.
- `deployments/api/tests/observability/test_instrumented_app.py` — **new** regression tests A & B.
- `deployments/api/pyproject.toml` — bump OTel instrumentation floors (lines 15–16).
- `uv.lock` (repo root) — regenerated by `uv lock`.

Reuse (do not reinvent): `register_middlewares` (`middleware.py:23`), `instrument_fastapi`
(`observability/tracing.py:123`), `base_router` (`main.py:19-23`), the dependency-override and
`_ALL_LICENSED_CLAIMS`/`test_user` patterns in `tests/conftest.py`, and the preflight-request
shape in `tests/test_middleware.py:42-48`.

## Verification

1. **Reproduce first (red):** with the factory + tests in place but *before* Step 3, run the
   exact target so fastapi 0.139.2 is used:
   `make api-test-exact` (or `uv run --package stitch-api --exact --group dev pytest deployments/api/tests/observability/test_instrumented_app.py`).
   Confirm **Test A fails** with the `_IncludedRouter` `AttributeError` 500 — proving it catches
   the regression.
2. **Apply Step 3**, then re-run `make api-test-exact` — Test A (405) and Test B (2xx + CORS
   header) both pass, and the full api suite stays green. `uv lock --check` passes.
3. **End-to-end:** `make reboot-docker` on this branch; watch `api-1` logs — no more
   `AttributeError: '_IncludedRouter' object has no attribute 'path'` / `Exception in ASGI application`.
4. Manual preflight (should be 2xx **with** `access-control-allow-origin`):
   ```
   curl -i -X OPTIONS http://localhost:8000/api/v1/auth/me \
     -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: authorization"
   ```
5. Authenticated call returns 200:
   `curl -i http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer <token from colophon 'Copy token'>"`.
6. In the app, open the colophon panel: `Auth Claims Status` is populated (no `Failed to fetch`),
   resources load.
7. Push the branch and confirm the PR preview reproduces the fix (same colophon check).

## Out of scope / notes (surfaced, not changed)

- **Benign log noise:** `Failed to export traces to otel-collector:4317 ... UNAVAILABLE` is just
  no local OTLP collector running; unrelated to this bug.
- **Host venv drift:** the on-disk `.venv` is `fastapi 0.136.1` while `uv.lock` is `0.139.2`. The
  Docker build and `--exact` test target use the lock, so services/CI are unaffected; if anyone
  runs the api directly on the host venv, `uv sync` reconciles it.
- **OTel global tracer provider:** `configure_tracing` sets a process-global provider that can't
  be cleanly reset (per `tests/observability/test_tracing.py:71-80`). The new tests avoid this by
  passing their own `TracerProvider()` to `create_app` and using `FastAPIInstrumentor.instrument_app`
  per-app-instance — no global uninstrument needed.
