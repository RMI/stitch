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
  never be served from rows built by older code. An operator can also switch
  the fast path off (`disabled`, see [Verifying](#verifying)); that stays off
  across rebuilds and deploys until someone switches it back on. Each API
  process re-checks readiness at most every 5 seconds, so changes to it take
  effect within that.
- **Staying current:** every write that can change a list answer (creating or
  attaching sources, re-ordering a field's sources, merging) locks the affected
  resources first, then recomputes their rows in the same transaction, so they
  commit together. Rows written by an older API revision still serving during a
  deploy carry that revision's commit, so the next rebuild finds and redoes
  them.
- **Unchanged:** the detail endpoint (`GET /oil-gas-fields/{id}`) and per-field
  source listings always compute live.

## Rolling it out

Every deploy of new code needs a full rebuild by that code before the fast path
comes back (each commit only trusts rows it built). Until CI runs it
automatically, do it by hand:

1. **Deploy as usual,** and wait until the previous API revision has stopped
   serving. Its writes refresh rows with the old rules, and one that lands after
   the rebuild marks the table ready would be served.
2. **Run `--if-stale`** from the deployed API image (see
   [Running a rebuild](#running-a-rebuild)). Lists use live until it finishes
   (~1.5 minutes at 50K resources) — correct, just slower — then switch to the
   read model within a few seconds.
3. **Verify** (below). If anything looks wrong, switch the fast path off
   (below) and reads go back to live within a few seconds, and stay there
   through later deploys until you switch it back on.

## Running a rebuild

```bash
# Full rebuild (all resources). Safe while the API is serving traffic.
python -m stitch.api.db.read_model.rebuild

# Full rebuild only if it isn't already built by this code (the post-deploy step).
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

  Don't run a rebuild from a *different* image while the old one is still
  serving: an old API process that checked readiness in the last 5 seconds
  keeps trusting the table, and can read rows the new code has just rewritten.
  Deploys wait for the previous revision to stop serving before rebuilding (see
  [Rolling it out](#rolling-it-out)); do the same whenever you rebuild by hand.

- **What happens:** readiness is cleared first, so reads switch to live for the
  duration. Resources are rebuilt in committed batches (`--batch-size`,
  default 500), each batch replacing its resources' rows. Then it checks for
  resources whose rows were since rewritten by other code (an older API
  revision still serving writes, or an `--ids` repair run from another image)
  and redoes those, repeating until none are left. The last of these checks
  happens in the same transaction that sets readiness, so no repair can slip in
  between: rows for resources that are no longer listable are removed, the
  result is checked (every listable resource has all four rows, all computed by
  this code, and nothing else has any), and only then is readiness set. The
  table is never emptied along the way, so a reader that checked readiness just
  before the rebuild started still finds a row for every resource. At ~50K
  resources it takes about 1.5 minutes.
- **Full rebuild vs `--if-stale`:** a plain full rebuild recomputes every
  resource. `--if-stale` only recomputes resources not already computed by this
  code, so re-running it after a failed or cancelled run picks up where that run
  stopped.
- **If it fails:** readiness stays cleared and reads stay live; just run it again.
  Whatever rows a failed run leaves are never served, and the next run replaces
  or reuses them. If other code keeps rewriting rows, it stops after 5 passes
  with an error asking whether an older API version is still serving writes.
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
- `--ids` never changes readiness, and is safe while the API serves reads. It
  reports which ids it recomputed and which aren't listed (merged away, or no
  active sources — any stored rows for those are removed). It changes nothing
  and exits with an error if any id doesn't exist (usually a typo), or if the
  table is ready but was built by different code (even if switched off, since
  switching it back on serves those rows): run it from the same image as the
  API, so the table never mixes two versions. During a full rebuild the
  table isn't ready, so a repair from any image runs; the rebuild waits for it
  and redoes its rows before finishing. A repair that starts just as a rebuild
  finishes waits for it, then refuses if that rebuild was by other code.
- Expected failures (another rebuild running, a failed integrity check, rows
  still rewritten by other code after 5 passes, unknown ids, a table built by
  other code) print as a single `ERROR` line; unexpected ones (e.g. the
  database is unreachable) show a traceback. Either way it exits with status 1.
  Invalid arguments print the usage and exit with status 2.

## Verifying

```sql
-- Ready, when it was last rebuilt, by which commit (compare with
-- build.git_sha from the API's health endpoint), and whether it's switched off
SELECT ready, rebuilt_at, code_version, disabled FROM og_field_resource_state_status;

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

-- Every row computed by the serving commit (expect 0)
SELECT count(*) FROM og_field_resource_state s, og_field_resource_state_status st
WHERE s.code_version IS DISTINCT FROM st.code_version;
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
UPDATE og_field_resource_state_status SET disabled = true;
```

It stays off until you switch it back on. Rebuilds still run and keep the rows
current, but never switch it back on; they log a warning saying it's off. Once
the problem is fixed and a rebuild by the deployed code has finished:

```sql
UPDATE og_field_resource_state_status SET disabled = false;
```

(Setting `ready = false` instead only lasts until the next rebuild.)

## When a full rebuild is needed again

Ordinary API writes keep the table current. Beyond that:

- **Every deploy of new code** needs a rebuild before the fast path comes back
  (see readiness above). This covers changes to how answers are computed and
  migrations alike — nothing else needs to clear readiness.
- **A database restore, or manual SQL edits** to sources, memberships, or
  priorities, change answers without the code or the writes noticing: run a
  plain full rebuild (or `--ids` for the affected resources). Not `--if-stale`:
  rows already computed by this code would be skipped, even though the data
  under them changed.

## Changing the code safely

- **New write path** that can change a list answer (a source value, membership,
  priority, or merge state): first call `lock_resources` from
  `db/read_model/state.py` for the affected resources, before reading or
  writing anything (so a writer that waited reads the other's committed
  changes, e.g. a merge); then call
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
  takes ~85 ms at 50K resources, almost all of it finding the resource's
  memberships, because `og_field_memberships` has no index on `resource_id`.
  The unique `(resource_id, source_pk)` constraint from the separate DB-cleanup
  work (#322) provides one; with it the refresh drops to ~16 ms per resource
  (~24 ms for a three-resource merge).
- **Sorting by fields other than `name`** has no index (30–100 ms). Add
  per-direction indexes only if usage shows those sorts matter.
- **`q=` text search** scans the profile's rows (50–150 ms); a btree index can't
  help a substring match. A trigram index (`pg_trgm`) is the likely fix if needed.
- **The live list's count query** sorts every matching row before counting (the
  read model's count doesn't). Worth fixing on the live path separately.
