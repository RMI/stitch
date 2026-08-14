# Entity linkage: survivable runs and self-describing failures

## Context

The entity-linkage bulk pass in the PR-0224 preview environment ran for 5h37m and
died with `state=failed`, a blank `error`, and no result. Log Analytics gave us the
traceback: `httpx.ReadTimeout` raised at `matching.py:75` — the inner `q=` superset
scan — after the downstream `GET /api/v1/oil-gas-fields/` exceeded the client's
hardcoded 30s timeout.

The query logs reconcile exactly: every request was **two database queries and
nothing else** (the per-page `COUNT` plus the page itself), each running ~10s for
minutes before the failure. The fatal request was 9.0s + 22.5s = 31.6s. The API
completed it; entity-linkage had already hung up at 30s.

Three defects turned one slow query into a lost 5.6-hour run:

1. **The failure was invisible.** `jobs.py` records `str(exc)`, and httpx timeout
   exceptions stringify to `""`. The job record said only "failed" — no type, no
   traceback, no indication of how far the run got. Diagnosing it required Azure.
2. **A single transient failure is fatal.** `_request_json` has no retry at all,
   and the 30s timeout is hardcoded and unconfigurable.
3. **The inner scan is under-paged.** It silently runs at the client default page
   size of 50 while the outer loop uses 200, quadrupling round trips and per-page
   `COUNT` queries on the hot path.

This plan covers those three. It deliberately does **not** fix the root cause — the
unindexed leading-wildcard ILIKE across five columns (`queries.py:451-454`) that
makes the pass take hours in the first place, tracked as STIT-573. That is an
architectural change needing its own design discussion per `CONTRIBUTING.md`.

**Intended outcome:** a linkage run survives transient downstream blips, reports its
progress while running, and — when it does fail — says exactly what happened and how
far it got, without anyone opening Log Analytics.

---

## Setup

Branch from `main` (not the `next` release branch), in a worktree under the repo per
project convention. Directory name mirrors the existing `feat+hide-merge-candidates`
style, since a `/` in the branch name can't be a single directory component:

```bash
git worktree add .claude/worktrees/fix+el-failure -b fix/el-failure main
```

Then bootstrap it (`HACKING.md` first-time setup):

```bash
cd .claude/worktrees/fix+el-failure && cp env.example .env && make uv-sync-dev
```

All paths below are relative to the worktree root.

---

## Commit 1 — `fix(entity-linkage): record exception type on failed jobs`

The smallest, highest-value change: a failed run can never again report a blank error.

**`deployments/entity-linkage/src/stitch/entity_linkage/jobs.py`**

Replace the bare `str(exc)` at line 88 with a module-level helper (not a new
abstraction — one function, next to its only caller):

```python
def _format_exception(exc: BaseException) -> str:
    """Never empty: httpx timeout exceptions stringify to ''."""
    message = str(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
```

**`deployments/entity-linkage/tests/test_jobs.py`**

The assertion at line 71, `error == "kaboom"`, becomes `"RuntimeError: kaboom"`. Add
a case raising an exception with an empty message (`httpx.ReadTimeout("")` — the
actual incident shape) and assert the recorded error is still non-empty.

---

## Commit 2 — `feat(entity-linkage): report live progress during a linkage pass`

Makes an in-flight run observable, and a failed run self-reporting about how far it
got. Independently useful even if nothing else lands.

**`entity_linkage/entities.py`** — add alongside the existing `BulkLinkResponse`:

```python
class LinkProgress(BaseModel):
    """Live counters for an in-flight pass. Mutated in place by link_all."""
    resources_scanned: int = 0
    match_groups_found: int = 0
    merge_candidates_created: int = 0
    merge_candidates_skipped: int = 0
    last_resource_id: int | None = None
```

**`entity_linkage/jobs.py`** — add an optional field to `JobRecord`, kept generic so
the manager stays task-agnostic (it already documents itself as generic):

```python
progress: SerializeAsAny[BaseModel] | None = None
```

`JobManager.start` gains a matching `progress: BaseModel | None = None` parameter it
stores on the record. The caller owns the object and mutates it; the manager only
serializes it.

**`entity_linkage/matching.py`** — `link_all` gains `progress: LinkProgress | None = None`
and updates it in the loop alongside the existing local counters. Emit a periodic
structured log **every 100 resources** (`_PROGRESS_LOG_EVERY = 100`), using the repo's
existing event pattern — `extra={"event": {...}}`, flattened to top-level JSON keys by
the shared `JsonFormatter`:

```python
logger.info("linkage_progress", extra={"event": progress.model_dump()})
```

This is what makes the next incident diagnosable from EL's own logs. Today EL logs
nothing during a run — all ~14k of its log lines in the incident window were inbound
status polls.

**`entity_linkage/routers/link.py`** — `start_link_all` constructs one `LinkProgress`
and passes it into both `link_all` and `get_job_manager().start(...)`, so the status
endpoint serializes live counters on every poll.

**Frontend:** no change required. `EntityLinkagePage.jsx` renders
`<StructuredDataView data={record} />` for the whole record, so `progress` appears
automatically under "Job status". Optionally surface `resources_scanned` in the
`state === "running"` branch, which currently shows only static text — small, and
worth folding in here if it's cheap.

**Tests** — `deployments/entity-linkage/tests/test_matching.py`: assert `LinkProgress`
counters match the returned `BulkLinkResponse` at the end of a pass.
`tests/test_jobs.py`: assert `progress` round-trips onto the record.

---

## Commit 3 — `feat(client): retry transient transport failures on idempotent requests`

Shared-package change, no consumer wiring yet, so it reviews on its own.

**`packages/stitch-client/src/stitch/client/async_client.py`**

Add bounded retry with exponential backoff to `_request_json`. Hand-rolled, following
the existing `wait_for_health` retry loop in this same file — the repo has no
`tenacity`/`backoff` dependency and `AGENTS.md` says not to add one when existing code
suffices.

Two constraints that matter:

- **Catch `httpx.TransportError` only.** It is the parent of `TimeoutException`
  (covering `ReadTimeout`/`ConnectTimeout`/`PoolTimeout`), `NetworkError`, and
  `ProtocolError` — one clause covers every transport failure. HTTP error *statuses*
  must keep flowing through `_raise_for_status` unretried; a 4xx is not transient, and
  `_submit_group` depends on seeing a 400 verbatim.
- **Retry idempotent methods only** (`GET`/`HEAD`/`OPTIONS`). A timed-out
  `POST /merge-candidates` may have succeeded server-side; retrying risks duplicates.
  The API's duplicate-fingerprint 400 gives partial cover, but that's not a guarantee
  worth leaning on.

Log every retry with `type(exc).__name__` — same reason as commit 1, `str(exc)` on a
timeout is empty and would produce a useless log line.

New constructor parameters: `max_retries: int = 2`, `retry_base_delay: float = 0.5`,
`retry_max_delay: float = 5.0`. These must apply in **both** constructor branches,
including when the caller supplies its own `httpx.AsyncClient` — unlike `timeout`,
retry behavior is independent of the transport.

**Blast radius:** three consumers — `entity-linkage`, `seed`, `stitch-llm`.
`stitch-llm` serves interactive requests, so under a downstream outage a user-facing
call now takes up to ~3× longer before failing; `max_retries=2` with a 0.5s base bounds
that at roughly +1.5s. Call it out in the PR description; if unwelcome, `stitch-llm`
can pass `max_retries=0`.

**Tests** — `packages/stitch-client/tests/test_async_client.py`. The existing
`make_client` helper wraps `httpx.MockTransport`, which is ideal. Add: a GET that
raises `httpx.ReadTimeout` once then succeeds (assert call count); a GET that exhausts
retries and re-raises; a POST that raises and is **not** retried; a 400 that surfaces
as `StitchAPIError` with no retry.

---

## Commit 4 — `feat(entity-linkage): make downstream timeout and retries configurable`

**`entity_linkage/settings.py`** — the 30s timeout is currently hardcoded at
`client.py:36`. Promote it, next to the existing `api_base_url`:

```python
api_timeout_seconds: float = Field(default=30.0, alias="ENTITY_LINKAGE_API_TIMEOUT_SECONDS")
api_max_retries: int = Field(default=2, alias="ENTITY_LINKAGE_API_MAX_RETRIES")
```

**`entity_linkage/client.py`** consumes both. Document them in `env.example` and
`deployments/entity-linkage/README.md`.

**Be honest in the commit message about what this buys.** Retry converts a transient
blip into a survivable event. It does **not** rescue a run whose queries genuinely
exceed the timeout — the logs show requests steadily taking 19–31s before the failure,
so a retry there just burns more time and fails again. Raising
`ENTITY_LINKAGE_API_TIMEOUT_SECONDS` is an operational lever, not a fix; it makes an
already-too-long run longer. The actual fix is STIT-573.

---

## Commit 5 — `perf(entity-linkage): use the run's page size for the inner match scan`

**`entity_linkage/matching.py`** — `find_match_group_for_resource` calls
`client.iter_oil_gas_fields(q=seed_name)` with no `page_size`, so it uses the client
default of 50 while the outer driver loop uses the requested 200. Thread `page_size`
through `find_match_group_for_resource` and `link_resource` so the inner scan uses the
same value. `link_one` (the single-resource route) takes the same default so both
paths behave identically.

This is the hot path — once per resource, each page costing a `COUNT` plus the page
query. Cutting pages 4× cuts that `COUNT` work 4×. It does not change the per-page
ILIKE cost, so it's a constant-factor win, not a fix.

**Tests** — `tests/test_matching.py`: assert the inner scan is invoked with the run's
`page_size`.

---

## Verification

Run after each commit, not just at the end:

```bash
make check
```

**End-to-end locally:**

```bash
make dev-docker
```

Start a run from the UI at `http://localhost:3000` (Entity Linkage → Start run) and
confirm, while it is running, that "Job status" shows `progress.resources_scanned`
climbing on each 2s poll, and that `linkage_progress` events appear every 100
resources:

```bash
make follow-stack-logs
```

**Failure path** — the case that started all this. Point entity-linkage at a
deliberately unreachable API, confirm the run fails with a typed, non-empty error
(e.g. `ConnectError: ...`) rather than a blank field, that retry attempts are visible
in the logs, and that `progress` shows how far it got:

```bash
ENTITY_LINKAGE_API_BASE_URL=http://127.0.0.1:9/api/v1 ENTITY_LINKAGE_API_MAX_RETRIES=2 make api-dev
```

**Deployed** — once this reaches a preview environment, the same KQL used to diagnose
the original incident should show progress events from the `-el` container app, making
run throughput observable without touching the API side:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s endswith "-el"
| extend p = parse_json(Log_s)
| where tostring(p.msg) == "linkage_progress"
| project TimeGenerated, scanned = toint(p.resources_scanned), groups = toint(p.match_groups_found)
| order by TimeGenerated asc
```

---

## Out of scope (deliberately)

- **STIT-573 / the ILIKE root cause.** Separate design discussion.
- **The redundant per-page `COUNT`.** Roughly half of every request's database time,
  and `iter_oil_gas_fields` doesn't need it — `async_client.py:154-168` has two other
  termination conditions that suffice. An opt-in `include_total=false` query param
  would be ~2× on the hot path with no schema change or new index. Bigger than commit
  5, cheaper than STIT-573, but it's an API contract change (the frontend's pagination
  UI consumes `total_pages`) so it belongs with that discussion. **Worth raising as
  its own ticket.**
- **`_existing_fingerprints` unpaginated fetch** (`matching.py:154`) — pulls the entire
  merge-candidate list in one call. Harmless today, grows with the queue, will
  eventually time out on its own. Pre-existing; flagging, not fixing.
- **Job state is per-process and lost on restart** — already documented in the
  `jobs.py` docstring, and `max-replicas` is unset for the `-el` container app so the
  concurrency guard can't hold across replicas. Real, but independent of this failure
  (the run did stay on a single replica).
- **OTEL console span export doubles log volume** — roughly half the 662k API log lines
  in the incident window were duplicate `span` records. Worth an ingestion-cost look,
  unrelated to this bug.
