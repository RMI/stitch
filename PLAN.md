# STIT-573 — Entity linkage fails at production data scale

## Context

The entity-linkage service (`deployments/entity-linkage/`) reconciles source records
(GEM/`gem`, WoodMac/`wm`, regulator/`ccr`, plus `rmi`, `llm`) into resources and produces
merge candidates. Today its only entry point, `POST /api/v1/start`
([start.py:104](deployments/entity-linkage/src/stitch/entity_linkage/routers/start.py:104)),
runs the whole pass **synchronously in one request**:

1. `collect_oil_gas_fields` pulls the **entire** resource table into memory (default
   `max_pages=None`) — [async_client.py:109](packages/stitch-client/src/stitch/client/async_client.py:109).
2. groups exact case-insensitive duplicate names in memory (O(n) hash) — `start.py:51`.
3. serial N+1 detail fetch per candidate — `start.py:84`.

It succeeds at dev/staging volumes and fails at production scale. Root cause is **unbounded
in-memory materialization** (memory blowup) plus total round-trips/query cost — not a quadratic
algorithm.

**Fix strategy (agreed):** address the memory axis now by inverting the pass from
"load everything, then group" to a **bounded per-resource pass**, structured so the queue/async
work Jackson flagged ("this should become a queue") can wrap it later without a rewrite. The
per-ID endpoint becomes the natural unit-of-work a queue would enqueue.

**Success criterion:** a full-dataset linkage run at production scale completes and produces the
same merge candidates as today, with peak memory bounded to a single field's candidate shortlist
(independent of total dataset size). No new O(n)-in-memory accumulation anywhere on the path.

## Ticket drift (believe the code; flagged for the ticket)

- Bug says **"regulator sources"** → in code this is source key **`ccr`**. There are **five**
  source keys (`gem`, `wm`, `rmi`, `llm`, `ccr`), not three. Epic STIT-5's summary still says only
  "GEM and WoodMac." The three-source framing is stale.
- Bug describes an entity-linkage **"job" / "run"** → there is **no** job/CLI/scheduler/queue. It
  is a synchronous HTTP handler. Jackson's "should become a queue" is aspirational, confirmed
  greenfield (no celery/rq/arq/redis/BackgroundTasks anywhere).

## Approach

New per-resource endpoint on the entity-linkage service plus a convenience bulk endpoint that
iterates it, replacing the in-memory `/start` pass. All matching primitives already exist on the
main API; the main change is teaching the client to **filter server-side** instead of pulling the
whole table.

### Name-matching semantics (decided: superset + client re-filter)

The main API's `name`/`country` filters are **exact, case-sensitive** `== value`
([queries.py:296](deployments/api/src/stitch/api/db/queries.py:296)); `q` is case-insensitive
substring ILIKE over `Q_FIELDS` ([queries.py:290](deployments/api/src/stitch/api/db/queries.py:290)).
Today's grouping uses `name.strip().casefold()`
([entities.py:51](deployments/entity-linkage/src/stitch/entity_linkage/entities.py:51)).

To preserve exact current semantics without a main-API change: search the API with the
**case-insensitive superset** (`q=<name>` ILIKE, optionally `country=<country>` exact), then
**re-filter in bounded memory** to records whose `normalized_name` (casefold+strip) equals the
seed field's and whose normalized country matches. The superset per name is small, so memory stays
bounded.

> **Follow-up ticket (to open):** add a DB-side normalized-name match to the main API so the
> superset+refilter dance can be dropped. Out of scope for STIT-573.

## Changes by layer

### 1. Client — teach it to filter (`packages/stitch-client` + entity-linkage wrapper)

- `AsyncStitchClient` ([async_client.py:95](packages/stitch-client/src/stitch/client/async_client.py:95)):
  add filter params (`q`, `name`, `country`, …) to `list_oil_gas_fields_page` (pass through to the
  `params` dict), and add a `list_merge_candidates()` method (`GET /oil-gas-fields/merge-candidates`)
  for the queue-skip nice-to-have.
- `StitchApiClient` ([client.py:48](deployments/entity-linkage/src/stitch/entity_linkage/client.py:48)):
  mirror the new filter params on `list_oil_gas_fields_page`; add a `list_merge_candidates()`
  wrapper. `get_oil_gas_field_detail` and `create_merge_candidate` already exist and are reused.
- Keep the existing unbounded `collect_oil_gas_fields` for now (still used by `/start` until it is
  retired) but it must not be on the new path.

### 2. Per-resource matcher — new module + endpoint (entity-linkage service)

New router (e.g. `routers/link.py`), mounted in
[main.py:20](deployments/entity-linkage/src/stitch/entity_linkage/main.py:20) alongside `start_router`,
guarded by the same `SERVICE_ENTITY_LINKAGE_RUN` permission.

`POST /api/v1/oil-gas-fields/{id}` (final path shape TBD during impl) does, in bounded memory:
1. `get_oil_gas_field_detail(id)` → seed name + country.
2. candidate superset search: `list_oil_gas_fields_page(q=<name>, country=<country>, …)`, paging the
   (small) superset.
3. re-filter to exact `normalized_name` + normalized country equality (reuse `FieldCandidate.
   normalized_name` and `_normalize_country` from `start.py`; lift the shared helpers into the new
   module or a small `matching.py` so both paths use one implementation — remove the orphaned copy
   if `/start` is retired).
4. build the shortlist ids (seed + confirmed matches); if `len >= 2`, `create_merge_candidate(ids)`.
5. return a per-resource result (matched ids, whether a candidate was created/skipped).

Pull the matching helpers into one place; do not duplicate normalization logic.

### 3. Bulk convenience endpoint (entity-linkage service)

`POST /api/v1/oil-gas-fields` (bulk) iterates every resource id **page by page** (a generator over
`list_oil_gas_fields_page`, never accumulating the full set) and runs the per-resource matcher for
each, aggregating a summary. This fully replaces the `/start` in-memory pass.

- **Bounded memory:** process one page of ids at a time; the only cross-page state is a small
  `set[fingerprint]` of already-submitted merge groups to avoid redundant POST attempts within a run.
- **Dedup floor:** `merge_candidates` has a unique fingerprint constraint (sorted id set) that
  rejects duplicates at the DB ([merge_candidate_actions.py:79](deployments/api/src/stitch/api/db/merge_candidate_actions.py:79)),
  surfaced as a 4xx by `create_merge_candidate`
  ([oil_gas_fields.py:178](deployments/api/src/stitch/api/routers/oil_gas_fields.py:178)). The bulk
  loop must catch/skip that gracefully rather than abort the run.
- Decide during impl whether to retire `/start` now or leave it as a deprecated shim delegating to
  the bulk endpoint (prefer retiring to avoid two matching paths; remove orphaned code either way,
  per AGENTS.md).

**Scoping caveat (explicit):** the bulk endpoint fixes **memory**, not **wall-time** — it still runs
synchronously in one request, blocking the single uvicorn worker with no timeout bound. That is the
deferred "queue" axis; the per-resource endpoint is deliberately the unit a queue would later enqueue.

## Nice-to-haves (likely closed before opening for review; not committed)

- **Queue-skip:** before POSTing, read the candidates queue via `list_merge_candidates()` and skip
  groups whose fingerprint already exists — turns the fingerprint-constraint *raise* into a clean
  pre-check. Client + bulk-loop wiring above already sets this up.
- **Shared read cache:** cache read objects (candidate lists, details) across the bulk run to cut
  redundant round-trips. Low priority; acceptable to trade wall-time/network for deferring a broader
  caching design. Leave out unless cheap.

## Verification

- **Unit (entity-linkage):** matcher tests with a fake `StitchApiClient` — superset+refilter
  reproduces today's casefold/strip grouping (incl. case/whitespace variants the exact filter would
  miss), country confirmation, `min_length=2` guard, skip-on-existing. Follow existing patterns in
  `deployments/entity-linkage/tests/test_start.py` / `test_start_api.py` / `test_client.py`.
- **Unit (stitch-client):** filter params reach the request in
  `packages/stitch-client/tests/test_async_client.py`.
- **Equivalence:** on seed data, bulk endpoint produces the same merge-candidate set as `/start`.
- **Scale repro (end-to-end):** bring the stack up (`make dev-docker` / `--profile friends`), bump
  `SEED_FAKER_POST_COUNT` up the volume ladder from `deployments/PERFORMANCE.md` (1k → 8k → 50k),
  re-seed cumulatively, and confirm the bulk run completes at a volume where the old `/start` blows
  up, with bounded memory.
- `make check` (lint + tests + format + lockfile) before handing off.
