# DB read-performance refactor: precomputed ranked-candidate state table (STIT-766 alt)

## Context

The `list`, `filter-options`, and `detail` endpoints rebuild the same expensive
coalescing every request: a 5-table join (`memberships → resources → global
priority → source header → EAV values`), a `ROW_NUMBER()` window to pick the
priority winner per `(resource, field)`, then a pivot back to wide columns.
`deployments/PERFORMANCE.md` names the list CTE (`GET /api/v1/oil-gas-fields/`) as
the suspected hot path; it measured ~302ms mean and ~9× scaling from 1k→50k rows.

Michael's design (PR #279 / STIT-766, `docs/STIT-766-design.md`) precomputes one
`jsonb` record **per permission variant** per resource and moves the permission
model into the DB (`permission_mask`, `user_source_key_permission`, `source_keys`
tables). That is more machinery than the problem needs.

**This plan** takes the lighter path the user proposed: precompute the *ranked
candidate rows* per `(resource, field)`, truncated at the first public source, and
keep permission filtering in Python exactly as it works today.

### Why truncation-at-first-public is correct

Licensing today is a pre-ranking filter: `licensed_sources(claims)` becomes
`WHERE m.source IN (:licensed)` applied **before** the window
(`construct_base_query_statement`, [queries.py:156](deployments/api/src/stitch/api/db/queries.py)).
Public sources are licensed to everyone. So for any `(resource, field)` the only
rows that can ever win for *any* user are the restricted sources ranked above the
first public source, plus that first public source. Everything below it is dead
weight. Storing candidates down to and including the first public source, then
applying today's `IN (:licensed)` filter at read time and taking the top surviving
row, reproduces current behavior for every permission set — with **no permission
model in the DB**.

### Decisions locked with the user

- **Sync mechanism:** plain table + an app-invoked refresh function (variant B).
  Recomputed for affected resources in-transaction from the existing write paths.
- **Scope:** `list` + `filter-options` now; coalesced `detail` as a fast follow
  before merge (see Follow-ups). `detail` provenance and `field-sources` (curator
  paths that need rows *below* first public) stay on the live query.
- **public flag:** an `is_public_source` column on `og_field_source_priority` (per
  source key). Named in full to avoid misreading a bare `public`.
- **Worktree:** `refactor/db-ranking-mv`.

## Success criteria

1. `list` and `filter-options` read from the precomputed table, not the live
   ranking CTE; the live 5-table CTE + window is no longer built per request for
   these two endpoints.
2. Byte-for-byte identical API responses for all permission sets (public,
   `wm`, `ccr`, `wm+ccr`) vs. today — enforced by the existing parity/licensing
   tests plus new ones.
3. The precomputed table is fully rebuildable from source-of-truth tables at any
   time, and a rebuild produces the same coalesced winners as the live query.
4. Curator edits (reprioritize, attach source, merge) are reflected immediately
   (same transaction) — no staleness.
5. The single source of truth for ranking stays in `queries.py`; the refresh
   reuses those builders (no re-implemented ranking SQL).

## Design

### New table: `og_field_resource_state`

Ranked candidate rows per `(resource, field)`, truncated at the first public
source. Only non-repointed resources with active memberships appear.

```
og_field_resource_state (
    resource_id  bigint      NOT NULL,   -- FK og_field_resources.id, ON DELETE CASCADE
    colname      varchar(50) NOT NULL,   -- attribute name (ck mirrors value table)
    rank         smallint    NOT NULL,   -- rn from _ranked(); 1 = top candidate
    source       varchar(10) NOT NULL,   -- source key; drives the read-time IN(:licensed) filter
    source_pk    bigint      NOT NULL,   -- FK oil_gas_field_sources.id; provenance
    value_text   varchar     NULL,
    value_num    double precision NULL,
    value_json   jsonb       NULL,
    PRIMARY KEY (resource_id, colname, source_pk)
)
-- read-time winner pick: WHERE source IN (:licensed) then top rank per (resource,colname)
CREATE INDEX ix_resource_state_pick ON og_field_resource_state (resource_id, colname, rank);
-- filter-options / licensing filter
CREATE INDEX ix_resource_state_source ON og_field_resource_state (source);
```

- `rank` is the `rn` from the existing `_ranked()` window computed over the
  **full** candidate set (no licensing), so removing unlicensed rows at read time
  and taking the min surviving `rank` yields the correct per-user winner.
- Model file: `deployments/api/src/stitch/api/db/model/og_field_resource_state.py`,
  registered in `db/model/__init__.py`. Follow existing model/mixin conventions
  (no audit columns needed — it is derived data).

### `is_public_source` flag on `og_field_source_priority`

Add `is_public_source boolean NOT NULL` to
[og_field_source_priority.py](deployments/api/src/stitch/api/db/model/og_field_source_priority.py).
Seed from a canonical set alongside `SOURCE_PRIORITY` in
[packages/stitch-ogsi/.../model/__init__.py](packages/stitch-ogsi/src/stitch/ogsi/model/__init__.py):
restricted = `{wm, ccr}` → `false`; `{rmi, bc, alb, nor, gem, llm}` → `true`.
Add a `PUBLIC_SOURCES`/`RESTRICTED_SOURCES` constant next to `SOURCE_PRIORITY` as
the single source of truth (used by the seed migration and any assertions).

### Builders in `queries.py` (reuse, don't re-implement)

1. **Refresh SELECT** — new builder, e.g. `resource_state_rows(resource_ids)`:
   - Start from `_ranked(construct_base_query_statement(licensed_sources=None,
     resource_ids=ids))` — **no** licensing filter (store all candidates).
   - Join `og_field_source_priority.is_public_source`; add
     `min(rank) FILTER (WHERE is_public_source) OVER (PARTITION BY resource_id,
     colname)` as `first_public_rank`; keep rows where `rank <= first_public_rank`.
   - Project the table's columns. This is the only new ranking-adjacent SQL and it
     is built on the existing `_ranked` CTE, so the winner logic never forks.

2. **Read from state** — new builder returning the same shape as
   `add_ranking(construct_base_query_statement(...))` produces today
   (`resource_id, colname, value_text, value_num, value_json, source, source_pk`),
   but sourced from `og_field_resource_state`:
   `SELECT DISTINCT ON (resource_id, colname) ... WHERE source IN (:licensed)
   ORDER BY resource_id, colname, rank`.
   - Rewire `base_resource_query` (list) and `filter_option_rows` to consume this
     instead of the live ranked CTE. The pivot helper `_add_pivot_columns` and the
     filter/sort builders are reused unchanged (same column shape).
   - `coalesced_winner_rows`, `coalesced_candidate_rows`, `field_source_candidates`
     stay live (detail + field-sources), unchanged.

### Refresh function + write-path wiring

`refresh_resource_state(session, resource_ids)` (new module
`deployments/api/src/stitch/api/db/resource_state.py`):
`DELETE FROM og_field_resource_state WHERE resource_id = ANY(:ids)` then
`INSERT ... SELECT resource_state_rows(:ids)`. Wrapped in a `named_query(...)`
scope for observability. Refreshing a now-repointed id re-runs the SELECT (which
filters `repointed_id IS NULL`) and inserts zero rows — an effective delete, so
merge needs no special-casing.

Call it in-transaction (before the actions' existing flush/commit boundary) from
every write that changes coalesced output:

| Write path | File | Affected ids |
|---|---|---|
| `set_field_source_priority` | [og_field_resource_actions.py:234](deployments/api/src/stitch/api/db/og_field_resource_actions.py) | `[id]` |
| `create` → attach | [og_field_resource_actions.py:326](deployments/api/src/stitch/api/db/og_field_resource_actions.py) | new resource id |
| `attach_sources_to_resource` | [og_field_source_actions.py:199](deployments/api/src/stitch/api/db/og_field_source_actions.py) | target resource id |
| `create_and_attach_source(s)` | [og_field_source_actions.py:66/107](deployments/api/src/stitch/api/db/og_field_source_actions.py) | attached resource id(s) |
| `apply_resource_merge` | [og_field_resource_actions.py:357](deployments/api/src/stitch/api/db/og_field_resource_actions.py) | `[*unique_ids, new_resource.id]` |

A test asserting each of these leaves the state table consistent with a live
recompute guards against a future write path forgetting to call it.

### Migration + backfill

Alembic migration under `deployments/api/alembic/versions/`:
1. Add `is_public_source` to `og_field_source_priority`; backfill from the
   canonical set.
2. Create `og_field_resource_state` + indexes.
3. Backfill: execute the compiled `resource_state_rows(all_root_ids)` builder via
   `op.get_bind().execute(...)` so the backfill uses the same SQL as the runtime
   refresh (no duplicated raw ranking SQL). Follow the repo convention: `downgrade`
   raises `RuntimeError`.

Expose `rebuild_all_resource_state(session)` (calls the refresh for all root ids)
for tests and for the seed tooling.

### Seed + observability

- `deployments/seed` posts through the API create/attach path, so per-resource
  refresh fires naturally. For the large `SEED_FAKER_POST_COUNT` ladders, add a
  single `rebuild_all_resource_state` call at end-of-seed to avoid per-POST
  overhead dominating (and to validate the batch rebuild path).
- Keep feeding query instrumentation: wrap new reads/refresh in `named_query`
  labels (e.g. `resources.list_ids`, `resources.filter_options`,
  `resources.state.refresh`) per
  [observability/context.py](deployments/api/src/stitch/api/observability/context.py);
  update `tests/observability/test_query_name_actions.py` for new labels.

## Verification

1. **Unit/query tests** (`deployments/api/tests/db/`):
   - New `test_resource_state.py`: `resource_state_rows` truncates at first public;
     rebuild is idempotent; refresh of a repointed id empties its rows.
   - Extend `test_resource_actions.py`: list/filter-options results identical
     across permission sets; licensing fall-through
     (`test_licensing_promotes_next_priority_value`) still passes off the table.
   - The N+1 guards
     (`test_query_hydration_round_trips_constant_in_page_size`,
     `test_detail_hydration_round_trips_constant_in_source_count`) stay green.
   - `TestCoalescingEngineParity::test_list_and_detail_agree_on_coalesced_winner`
     is the cross-check between the table-backed list and the live detail — must
     stay green.
2. **Write-path consistency tests**: after each write action above, the state
   table equals a fresh `rebuild_all_resource_state` for the touched resources.
3. **End-to-end**: `make api-dev`, seed a mixed dataset, hit
   `GET /oil-gas-fields/` and `/filter-options` with tokens for public / `wm` /
   `ccr` / `wm+ccr` and diff responses against `main`. Re-run
   `tools/analyze_logs.py` per `PERFORMANCE.md` to confirm the list CTE is gone
   and latency dropped.
4. `make check` (lint + tests + format + lockfile) before handing back.

## Follow-ups (explicitly out of this change)

- Coalesced `detail` read from the state table (planned before merge; detail's raw
  `source_data` and `field-sources` stay live since they need rows below the first
  public source).
- Any consolidation of the permission model — untouched here by design.

## Notes

- Work in worktree `refactor/db-ranking-mv` (under `.claude/worktrees/`).
- Do not commit/push; leave changes in the working tree for the user to review.
