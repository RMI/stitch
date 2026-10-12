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
  full rebuild sets `ready = true`; a missing row or `false` means "use live".
- **Staying current:** every write that can change a list answer (creating or
  attaching sources, re-ordering a field's sources, merging) recomputes the
  affected resources' rows in the same transaction, so they commit together.
- **Unchanged:** the detail endpoint (`GET /oil-gas-fields/{id}`) and per-field
  source listings always compute live.

## Rolling it out

1. **Deploy as usual.** CI runs the migrations (`76427dd73cbc` creates the table
   with `ready = false`) and deploys the API. Reads keep using live — nothing
   changes for users yet.
2. **Run a full rebuild** against the deployed database (below). This is a
   required step: until it succeeds, the fast path stays off.
3. **Verify** (below). If anything looks wrong, clear readiness (below) and reads
   go back to live immediately.

## Running a rebuild

```bash
# Full rebuild (all resources). Safe while the API is serving traffic.
python -m stitch.api.db.read_model.rebuild

# Recompute specific resources only (e.g. after fixing data by hand).
python -m stitch.api.db.read_model.rebuild --ids 123 456
```

- **Where to run it:** anywhere with the API's code and database settings. For a
  deployed lane, the same way CI runs migrations — the `api` image with the
  lane's `POSTGRES_*` variables, as `stitch_app` or `stitch_migrator`:

  ```bash
  docker run --rm -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD -e PGSSLMODE <api-image> python -m stitch.api.db.read_model.rebuild
  ```

  Locally, against the docker-compose database:

  ```bash
  POSTGRES_HOST=127.0.0.1 POSTGRES_USER=stitch_app uv run --env-file .env -- python -m stitch.api.db.read_model.rebuild
  ```

- **What happens:** readiness is cleared first, so reads switch to live for the
  duration. Resources are rebuilt in committed batches (`--batch-size`, default
  500), the result is checked (every listable resource has all four rows, nothing
  else has any), and only then is readiness set. At ~50K resources it takes about
  1.5 minutes.
- **If it fails:** readiness stays cleared and reads stay live; just run it again.
  Leftover rows from a failed run are never served and get overwritten.
- **Two at once:** a second full rebuild started while one is running exits with
  "Another resource-state rebuild is already running."
- `--ids` never changes readiness; it's safe at any time.

## Verifying

```sql
-- Ready, and when it was last rebuilt
SELECT ready, rebuilt_at FROM og_field_resource_state_status;

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

Then smoke-test the list and filter-options pages, and check the
`resources.count` / `resources.list_ids` / `resources.list_hydrate` /
`resources.filter_options` query timings (see `deployments/PERFORMANCE.md`).

**To switch the fast path off** without deleting anything:

```sql
UPDATE og_field_resource_state_status SET ready = false;
```

## When a full rebuild is needed again

Ordinary API writes keep the table current. Run a full rebuild after anything
that changes answers *without* going through those writes:

- a change to how winners are chosen (coalescing logic);
- a migration that changes default source priority (`og_field_source_priority`);
- a database restore, or manual SQL edits to sources, memberships, or priorities;
- adding a field to `OilGasFieldBase`, or a new source key.

A migration that changes answers should also clear readiness, so reads go live
until the rebuild runs:

```python
op.execute("UPDATE og_field_resource_state_status SET ready = false")
```

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
concurrency, JSONB output) and are skipped unless pointed at a disposable
database; they create and drop their own schema:

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
- **Write overhead:** each write's refresh takes ~85 ms at 50K, almost all of it
  finding the resource's memberships without an index. With a
  `(resource_id, status)` index on `og_field_memberships` (being added in the
  separate DB-cleanup work) it drops to ~16 ms.
- **Sorting by fields other than `name`** has no index (30–100 ms). Add
  per-direction indexes only if usage shows those sorts matter.
- **`q=` text search** scans the profile's rows (50–150 ms); a btree index can't
  help a substring match. A trigram index (`pg_trgm`) is the likely fix if needed.
- **The live list's count query** sorts every matching row before counting (the
  read model's count doesn't). Worth fixing on the live path separately.
