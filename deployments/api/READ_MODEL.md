# Resource-state read model

The oil & gas field **list** and **filter-options** endpoints are served from a
precomputed table, `og_field_resource_state`, instead of working out every
field's winning value on each request. At ~50K resources this takes typical list
requests from ~2–3 s to under 10 ms (see [Performance](#performance-at-50k-resources)).

The table is derived data: everything in it can be rebuilt from the
authoritative tables (sources, memberships, priorities) at any time. The detail
endpoint (`GET /oil-gas-fields/{id}`) and the per-field source listings don't
use it; they coalesce on every request.

## How it works

- **What's stored:** one row per resource *per permission profile*, holding each
  field's winning value and which source it came from (`provenance`). There are
  four profiles: all six public sources, plus any combination of the two
  restricted sources (`wm`, `ccr`). See `db/read_model/permissions.py`.
- **Who can list:** a caller whose licensed sources *exactly* match one of the
  four profiles. Anyone else gets a **403** that names the problem: a caller
  missing a public source (including one with no source grants at all), or
  holding a source that isn't in any profile yet. A `source:read:<key>` grant
  for a key the code doesn't know is ignored before matching.
- **Staying current:** every write that can change a list answer (creating or
  attaching sources, re-ordering a field's sources, merging) locks the affected
  resources first, then recomputes their rows in the same transaction, so they
  commit together.
- **Rebuilds:** a full rebuild recomputes every listable resource. CI runs one
  after every API deploy (picking up any change to how answers are computed),
  and every 6 hours for the `main` and `production` deployments (repairing drift
  the writes can't see). Nothing waits on either.

## Running a rebuild

```bash
# Full rebuild (all resources). Safe while the API is serving traffic.
python -m stitch.api.db.read_model.rebuild

# Recompute specific resources only (e.g. after fixing data by hand).
python -m stitch.api.db.read_model.rebuild --ids 123 456
```

- **When to run one by hand:** after a database restore, or after editing
  sources, memberships, or priorities with SQL (for a handful of resources,
  `--ids` is enough). Either one changes answers without going through the
  write paths. CI's runs cover deploys and drift.
- **Where to run it:** with the same code the API is running. For a deployed
  lane, run the deployed `api` image the same way CI does (see
  `.github/workflows/rebuild-read-model.yml`), with the lane's `POSTGRES_*`
  variables, as `stitch_app`:

  ```bash
  docker run --rm -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD -e PGSSLMODE <api-image> python -m stitch.api.db.read_model.rebuild
  ```

  Locally, see `HACKING.md`.
- **What happens:** resources are rebuilt in committed batches (`--batch-size`,
  default 500), each batch replacing its resources' rows, then rows for
  resources that are no longer listable are removed. The table is never
  emptied, so the API keeps serving complete answers throughout: reads never
  wait, and a write waits at most for the batch holding its resource. At ~50K
  resources it takes about 1.5 minutes.
- **If it fails partway:** the batches it finished stay in place and every
  resource keeps its rows; just run it again.
- **Two at once** (e.g. a scheduled run during a deploy's): harmless, they just
  repeat work.
- **`--ids`** reports which ids it recomputed and which aren't listed (merged
  away, or no active sources; any stored rows for those are removed). It
  changes nothing and exits with an error if any id doesn't exist (usually a
  typo).
- **Errors:** an expected failure (unknown ids) prints as a single `ERROR` line;
  an unexpected one (e.g. the database is unreachable) shows a traceback.
  Either way it exits with status 1. Invalid arguments print the usage and exit
  with status 2.

## Verifying

```sql
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

In the query timings (see `deployments/PERFORMANCE.md`), a list request runs
`resources.count` and `resources.list_page`, and filter-options runs
`resources.filter_options`. The cost the read model adds to writes (and to
rebuild batches) is labeled `read_model.refresh`.

## Changing the code safely

- **New write path** that can change a list answer (a source value, membership,
  priority, or merge state): first call `lock_resources` from
  `db/read_model/state.py` for the affected resources, before reading or
  writing anything (so a writer that waited reads the other's committed
  changes, e.g. a merge); then call `refresh_resource_state(s)` in the same
  transaction; and add a case to `tests/db/read_model/test_mutations.py`.
  Editing a source's values in place affects *every* resource it is attached
  to — lock and refresh all of them.
- **New field** on `OilGasFieldBase`: add the column to `OGFieldResourceState`
  (an import-time check fails until you do) plus a migration. The rebuild after
  the deploy fills it.
- **New source key:** decide whether it's public or restricted in
  `db/read_model/permissions.py`. A test fails until you do; until then, anyone
  holding the new key gets a 403 from the list.

## Tests

The normal suite runs on SQLite. A few tests need real Postgres (what the row
locks do under concurrency). CI runs them on every PR against a throwaway
Postgres; locally they're skipped unless pointed at a disposable database. They
create and drop their own schema:

```bash
STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch uv run --package stitch-api pytest deployments/api/tests/db/read_model -q
```

## Performance at 50K resources

Measured October 2026 on a laptop (Postgres 17, local), against a restored copy
of the 50K-resource benchmark seed (52K listable resources, 1.4M source values).
Medians of 7 runs, full action call; both columns return identical results.

| Request | Coalesced per request (before) | Read model |
|---|---:|---:|
| List, default sort, page 1 | 2.0–2.7 s | 6–9 ms |
| List, page 500 | 2.1–2.9 s | 7–9 ms |
| List, filtered (country, basin) | 2.0–2.7 s | 4 ms |
| List, sorted by a field other than `name` | 2.0–2.6 s | 30–100 ms |
| List, `q=` text search | 2.2–2.9 s | 50–150 ms |
| Filter options | 0.4–0.5 s | 20–25 ms |

- Full rebuild: ~97 s, ~160 MB peak memory; the table is ~195 MB including
  indexes.
- Each write's refresh: ~16 ms per resource (~24 ms for a three-resource
  merge).

## Known limitations and follow-ups

- **First deploy:** the table starts empty, so lists are empty until the
  post-deploy rebuild finishes (about 2 minutes at 50K). Later deploys are
  unaffected.
- **During a deploy,** the previous API revision can keep serving briefly. Rows
  its writes recompute use its rules, and rows the new revision serves were
  computed by the old code until the post-deploy rebuild finishes. This only
  matters for a deploy that changes how answers are computed; the next rebuild
  (after the deploy, or within 6 hours) corrects it.
- **The scheduled rebuild** uses each deployment's image tag. If a deploy pushed
  its image and then failed, that tag is ahead of the running code until the
  next successful deploy.
- **Incremental `--since` repair** is not implemented: no timestamp can reliably
  catch every kind of change (STIT-809).
- **Sorting by fields other than `name`** has no index (30–100 ms). Add
  per-direction indexes only if usage shows those sorts matter.
- **`q=` text search** scans the profile's rows (50–150 ms); a btree index can't
  help a substring match. A trigram index (`pg_trgm`) is the likely fix if
  needed.
