# Resource-state read model

The oil & gas field **list** and **filter-options** endpoints are served from a
precomputed table, `og_field_resource_state`, instead of working out every field's
winning value on each request. At ~50K resources this takes typical list requests
from ~2–3 s to under 10 ms (see [Performance](#performance-at-50k-resources)).

The table is a cache, not a source of truth. Everything in it can be rebuilt from
the authoritative tables at any time, and when it can't be trusted the API simply
answers the slower way ("live"), with the same results.

## How it works

- **What's stored:** one row per resource *per permission profile*, holding each
  field's winning value and which source it came from (`provenance`). There are
  four profiles: all public sources, plus any combination of the two restricted
  sources (`wm`, `ccr`). See `db/read_model/permissions.py`.
- **Who gets the fast path:** a request whose licensed sources *exactly* match one
  of the four profiles, while the table is marked **ready**. Everyone else
  (partial or unusual grants, internal unscoped calls) gets the live answer.
- **Readiness:** a single row in `og_field_resource_state_status`. Only a complete
  full rebuild sets `ready = true`, and it records the commit of the code that
  ran it (`code_version`, from the image's `GIT_SHA`). The API uses the table
  only when it is ready **and** was built by the same commit the API is running;
  otherwise it answers live. So every deploy of new code switches reads to live
  until that code rebuilds the table — a change to how answers are computed can
  never be served from rows built by older code. Each API process re-checks
  readiness at most every 5 seconds, so changes to it take effect within that.
- **Staying current:** every write that can change a list answer (creating or
  attaching sources, re-ordering a field's sources, merging) recomputes the
  affected resources' rows in the same transaction, so they commit together.
- **Unchanged:** the detail endpoint (`GET /oil-gas-fields/{id}`) and per-field
  source listings always compute live.

## Rolling it out

Every deploy of new code needs a full rebuild by that code before the fast path
comes back (each commit only trusts rows it built). CI does this automatically:

1. **Deploy as usual.** CI runs the migrations and deploys the API, then the
   **Rebuild Read Model** job (`.github/workflows/rebuild-read-model.yml`) runs
   `python -m stitch.api.db.read_model.rebuild --if-stale` from the same API
   image. It waits for the API deploy so the previous revision, whose writes
   would refresh rows with the old code's rules, is gone first. Reads use live
   from the deploy until the rebuild finishes (~1.5–2 minutes at 50K resources
   after the deploy) — correct, just slower.
2. **If that job fails,** the deploy still goes out and lists stay on live.
   Re-run the job, or run the rebuild by hand from the deployed image (below).
3. **Verify** (below). If anything looks wrong, clear readiness (below) and reads
   go back to live immediately.

## Running a rebuild

```bash
# Full rebuild (all resources). Safe while the API is serving traffic.
python -m stitch.api.db.read_model.rebuild

# Full rebuild only if it isn't already built by this code (what CI runs).
python -m stitch.api.db.read_model.rebuild --if-stale

# Recompute specific resources only (e.g. after fixing data by hand).
python -m stitch.api.db.read_model.rebuild --ids 123 456
```

- **Where to run it:** with the *same code* the API is running, because the
  rebuild records its commit and the API only trusts rows built by its own
  commit. For a deployed lane, run the deployed `api` image (it carries the
  commit as `GIT_SHA`) the same way CI runs migrations, with the lane's
  `POSTGRES_*` variables, as `stitch_app` or `stitch_migrator`. A rebuild run
  from a laptop records `unknown` and leaves the deployed API on live.

  ```bash
  docker run --rm -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD -e PGSSLMODE <api-image> python -m stitch.api.db.read_model.rebuild
  ```

  Locally, see `HACKING.md`: run it inside the `api` container if the API runs
  in Docker, or on your machine if the API does:

  ```bash
  POSTGRES_HOST=127.0.0.1 POSTGRES_USER=stitch_app uv run --env-file .env -- python -m stitch.api.db.read_model.rebuild
  ```

- **What happens:** readiness is cleared first, so reads switch to live for the
  duration. Resources are rebuilt in committed batches (`--batch-size`, default
  500), each batch replacing its resources' rows; rows for resources that are no
  longer listable are removed; the result is checked (every listable resource
  has all four rows, nothing else has any), and only then is readiness set. The
  table is never emptied along the way, so a request already in progress when
  the rebuild starts still gets a complete answer. At ~50K resources it takes
  about 1.5 minutes.
- **If it fails:** readiness stays cleared and reads stay live; just run it again.
  Whatever rows a failed run leaves are never served, and the next run replaces
  them.
- **Two at once:** a full rebuild started by hand while another is running
  exits with "Another resource-state rebuild is already running." `--if-stale`
  (the deploy step) instead waits up to 10 minutes for it to finish, then checks
  again and does nothing if that rebuild already made the read model current.
- **A rebuild that dies mid-run** (e.g. a cancelled CI job) releases its lock
  within about a minute: the lock's connection asks Postgres to drop vanished
  clients quickly. If a lock still seems stuck, find the session holding it and,
  once you're sure no rebuild is running, end it:

  ```sql
  SELECT l.pid, a.state, a.backend_start, a.client_addr
  FROM pg_locks l JOIN pg_stat_activity a USING (pid)
  WHERE l.locktype = 'advisory' AND l.objid = 766001 AND l.granted;

  SELECT pg_terminate_backend(<pid>);
  ```
- `--ids` never changes readiness; it's safe at any time. It reports which ids it
  recomputed and which aren't listed (merged away, or no active sources — any
  stored rows for those are removed). If any id doesn't exist it changes nothing
  and exits with an error, since that's usually a typo.
- Errors print as a single `ERROR` line and exit with status 1.

## Verifying

```sql
-- Ready, when it was last rebuilt, and by which commit (compare with
-- build.git_sha from the API's health endpoint)
SELECT ready, rebuilt_at, code_version FROM og_field_resource_state_status;

-- Exactly 4 rows per listable resource
SELECT count(*) AS state_rows, count(DISTINCT resource_id) AS resources
FROM og_field_resource_state;
SELECT count(DISTINCT r.id) AS listable_resources
FROM og_field_resources r
JOIN og_field_memberships m ON m.resource_id = r.id
WHERE r.repointed_id IS NULL AND m.status = 'ACTIVE';

-- No merged-away resources (expect 0)
SELECT count(*) FROM og_field_resource_state s
JOIN og_field_resources r ON r.id = s.resource_id
WHERE r.repointed_id IS NOT NULL;
```

Then smoke-test the list and filter-options pages, and check the query timings
(see `deployments/PERFORMANCE.md`). Served from the read model, a list request
runs `resources.count` and `resources.list_page`; served live it runs
`resources.count`, `resources.list_ids` and `resources.list_hydrate`.
Filter-options is `resources.filter_options` either way. The cost the read
model adds to writes (and to rebuild batches) is labeled `read_model.refresh`.

**To switch the fast path off** without deleting anything (API processes pick
this up within about 5 seconds):

```sql
UPDATE og_field_resource_state_status SET ready = false;
```

## When a full rebuild is needed again

Ordinary API writes keep the table current. Beyond that:

- **Every deploy of new code** needs a rebuild before the fast path comes back
  (see readiness above); CI's Rebuild Read Model job runs it. This covers changes
  to how answers are computed and migrations alike — nothing else needs to clear
  readiness.
- **A database restore, or manual SQL edits** to sources, memberships, or
  priorities, change answers without the code or the writes noticing: run a
  full rebuild (or `--ids` for the affected resources).

## Changing the code safely

- **New write path** that can change a list answer (a source value, membership,
  priority, or merge state): first call `lock_resources` from
  `db/read_model/state.py` for the affected resources, before reading or
  writing anything (locking later lets concurrent writers deadlock); then call
  `refresh_resource_state(s)` in the same transaction; and add a case to
  `tests/db/read_model/test_mutations.py`. Editing a source's values in place
  affects *every* resource it is attached to — lock and refresh all of them.
- **New field** on `OilGasFieldBase`: add the column to `OGFieldResourceState`
  (an import-time check fails until you do) plus a migration, then rebuild.
- **New source key:** decide whether it's public or restricted in
  `db/read_model/permissions.py`. A test fails until you do; until then, anyone
  holding the new key gets the live path.

## Tests

The normal suite runs on SQLite. A few tests need real Postgres (row locks under
concurrency, separate statements seeing different moments, JSONB output). CI
runs them on every PR against a throwaway Postgres; locally they're skipped
unless pointed at a disposable database. They create and drop their own schema:

```bash
STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch uv run --package stitch-api pytest deployments/api/tests/db/read_model -q
```

## Performance at 50K resources

Measured October 2026 on a laptop (Postgres 17, local), against a restored copy of
the 50K-resource benchmark seed (52K listable resources, 1.4M source values).
Medians of 7 runs, full action call including the readiness check; both columns
return identical results.

| Request | Live | Read model |
|---|---:|---:|
| List, default sort, page 1 | 2.0–2.7 s | 6–9 ms |
| List, page 500 | 2.1–2.9 s | 7–9 ms |
| List, filtered (country, basin) | 2.0–2.7 s | 4 ms |
| List, sorted by a field other than `name` | 2.0–2.6 s | 30–100 ms |
| List, `q=` text search | 2.2–2.9 s | 50–150 ms |
| Filter options | 0.4–0.5 s | 20–25 ms |

Full rebuild: ~97 s, ~160 MB peak memory; the table is ~195 MB including indexes.

## Known limitations and follow-ups

- **Incremental `--since` repair** is not implemented: no timestamp can reliably
  catch every kind of change (STIT-809).
- **Write overhead:** each write's refresh (query label `read_model.refresh`)
  takes ~85 ms at 50K, almost all of it finding the resource's memberships,
  because `og_field_memberships` has no index on `resource_id`. The unique
  `(resource_id, source_pk)` constraint from the separate DB-cleanup work (#322)
  provides one; with it the refresh drops to ~16 ms per resource (~24 ms for a
  three-resource merge).
- **Sorting by fields other than `name`** has no index (30–100 ms). Add
  per-direction indexes only if usage shows those sorts matter.
- **`q=` text search** scans the profile's rows (50–150 ms); a btree index can't
  help a substring match. A trigram index (`pg_trgm`) is the likely fix if needed.
- **The live list's count query** sorts every matching row before counting (the
  read model's count doesn't). Worth fixing on the live path separately.
