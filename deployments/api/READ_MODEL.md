# Resource-state read model

The oil & gas field **list** and **filter-options** endpoints work out every
field's winning value on each request, which takes ~2–3 s at ~50K resources. The
read model is a precomputed table, `og_field_resource_state`, that those
endpoints can read instead.

The table is a cache, not a source of truth. Everything in it can be rebuilt from
the authoritative tables at any time, and when it can't be trusted the API simply
answers the slower way ("live"), with the same results.

So far the tables and the rebuild command exist. Nothing reads the table yet, and
API writes don't keep it current yet, so answers are unchanged.

## How it works

- **What's stored:** one row per resource *per permission profile*, holding each
  field's winning value and which source it came from (`provenance`). There are
  four profiles: all public sources, plus any combination of the two restricted
  sources (`wm`, `ccr`). See `db/read_model/permissions.py`. Only a request
  whose licensed sources *exactly* match one of the four profiles can be served
  from the table; everyone else gets the live answer.
- **Readiness:** a single row in `og_field_resource_state_status`. Only a complete
  full rebuild sets `ready = true`, recording the commit of the code that ran it
  (`code_version`). Each row also records the commit that computed it. The table
  may be used only when it is ready **and** was built by the same commit the API
  is running.

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
  rebuild records its commit and the read model only counts as ready for the
  commit that built it. For a deployed lane, run the deployed `api` image (it
  carries the commit as `GIT_SHA`) the same way CI runs migrations, with the
  lane's `POSTGRES_*` variables, as `stitch_app` or `stitch_migrator`. A rebuild
  run from a laptop records `unknown`, which matches no deployed commit.

  ```bash
  docker run --rm -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD -e PGSSLMODE <api-image> python -m stitch.api.db.read_model.rebuild
  ```

  Locally, run it inside the `api` container if the API runs in Docker, or on
  your machine if the API does:

  ```bash
  POSTGRES_HOST=127.0.0.1 POSTGRES_USER=stitch_app uv run --env-file .env -- python -m stitch.api.db.read_model.rebuild
  ```

- **What happens:** readiness is cleared first, so the table isn't used while
  it's rebuilt. Resources are rebuilt in committed batches (`--batch-size`,
  default 500), each batch replacing its resources' rows. Then it checks for
  resources whose rows were since rewritten by other code (an older API
  revision still serving writes) and redoes those, repeating until none are
  left; rows for resources that are no longer listable are removed; the result
  is checked (every listable resource has all four rows, all computed by this
  code, and nothing else has any), and only then is readiness set. The table is
  never emptied along the way, so a reader that checked readiness just before
  the rebuild started still finds a row for every resource. At ~50K resources
  it takes about 1.5 minutes.
- **Full rebuild vs `--if-stale`:** a plain full rebuild recomputes every
  resource. `--if-stale` only recomputes resources not already computed by this
  code, so re-running it after a failed or cancelled run picks up where that run
  stopped.
- **If it fails:** readiness stays cleared; just run it again. Whatever rows a
  failed run leaves are never used, and the next run replaces or reuses them. If
  other code keeps rewriting rows, it stops after 5 passes with an error asking
  whether an older API version is still serving writes.
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
  table is ready but was built by different code: run it from the same image
  as the API, so the table never mixes two versions.
- Errors print as a single `ERROR` line and exit with status 1.

## Changing the code safely

- **New field** on `OilGasFieldBase`: add the column to `OGFieldResourceState`
  (an import-time check fails until you do) plus a migration, then rebuild.
- **New source key:** decide whether it's public or restricted in
  `db/read_model/permissions.py`. A test fails until you do; until then, anyone
  holding the new key would get the live path.

## Tests

The normal suite runs on SQLite. A few tests need real Postgres (e.g. the rebuild
lock). CI runs them on every PR against a throwaway Postgres; locally they're
skipped unless pointed at a disposable database. They create and drop their own
schema:

```bash
STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch uv run --package stitch-api pytest deployments/api/tests/db/read_model -q
```
