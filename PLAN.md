# STIT-766 — Precomputed current-state read model + single priority store

Branch: `refactor/db-mv` · worktree under `stitch/.claude/worktrees/` · base `main` (migration head `71aa7ef8150b`)

## Context

`list`, `filter-options`, and `detail` all rebuild the same coalesced "current state" on
every request. `deployments/api/src/stitch/api/db/queries.py` joins membership → resource →
default priority → source → value, left-joins per-field overrides, ranks candidates with a
four-key `ROW_NUMBER()` window (`_ranked`, queries.py:196), and pivots winners into wide rows.
`filter-options` is the worst case: `filter_option_rows` (queries.py:266) ranks **every active
value row for six fields across the whole table** on every call, uncached. The DB is <100MB, so
this recompute-on-read is pure waste.

This plan does two things (the scope you chose, "A + B"):

- **A. Read model** — a precomputed, permission-scoped current-state **table** that `list` /
  `filter-options` read directly, giving the DB one stored answer per resource per permission
  profile. Kept current by an app-controlled update call inside the same write transaction.
- **B. Single priority store** — collapse `og_field_source_priority` (global defaults) +
  `og_field_resource_source_priority` (per-field overrides) into one
  `og_field_resource_attribute_priority` table at `(resource, colname, source_pk)` grain.

**Public wire behavior is unchanged.** Response models (`OGFieldListItemView`,
`OGFieldFilterOptionsResponse`, `OGFieldView`, `OGFieldDetailView`) and the REST surface stay
identical; we only change how they are produced. No frontend changes.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | A (read model) **and** B (single priority table) |
| Storage | Regular **table**, maintained by an app-controlled update call (not a PG materialized view) — real table in both Postgres and SQLite, targeted per-resource recompute |
| Record shape | **Typed columns** mirroring `OilGasFieldBase`; provenance (field→source key) as a compact jsonb map column |
| Permission model | Only `wm`/`ccr` vary; the other six keys are treated as one **public** tier → ≤4 variants per resource (`permission_mask`) |

## Success criteria

1. `list` and `filter-options` serve from the read model (no per-request ranking window).
2. For a seeded dataset, read-model-served `list` / `filter-options` / `GET /{id}` are **byte-identical**
   to today's live-coalesced responses, across all four permission profiles.
3. After every mutating action (create, attach, reprioritize, merge) the read model matches a
   full rebuild-from-scratch, within the same transaction.
4. `make check` green (lint + tests + format + lockfile).

---

## Read-model design

New table `og_field_resource_state` (model file `db/model/og_field_resource_state.py`):

- `resource_id` BIGINT, FK → `og_field_resources.id` ON DELETE CASCADE
- `permission_mask` SMALLINT — `wm` bit (2) | `ccr` bit (1); values 0/1/2/3
- one typed value column per `OilGasFieldBase` field (18 cols), types from `ATTRIBUTE_KINDS`
  (`db/model/oil_gas_field_source_value.py:41`) — reuse `PORTABLE_*` types
- `provenance` jsonb (`PORTABLE_JSON`) — `{field: source_key | null}` for the list `provenance`
  map; not filtered/sorted, so jsonb is fine
- PK `(resource_id, permission_mask)`; indexes to serve `filter-options` distincts
  (`(permission_mask, <filter_field>)` per `FILTER_OPTION_FIELDS`)
- Only rows for **unmerged** resources (`repointed_id IS NULL`); merging deletes the rows.

**permission_mask semantics** (new module `db/read_model/permissions.py`, referencing
`OGSISrcKey`): `PUBLIC_SOURCES = all 8 − {wm, ccr}`. Each mask's visible-source set:

- 0 → public · 1 → public+ccr · 2 → public+wm · 3 → all 8

Build computes ≤4 variants per resource by running today's coalescer restricted to each mask's
visible sources. Store one row per `(resource, mask)` (≤4×resources; dedup deferred — trivial at
this size).

**Read path — mask + safety fallback.** From the caller's `licensed_sources`
(`api/permissions/__init__.py:12`) compute `mask = 2*('wm' in s) + 1*('ccr' in s)`. Fast path
only when the caller's non-wm/ccr grants exactly equal `PUBLIC_SOURCES` (the confirmed
operational invariant). If they don't (grants ever diverge), **fall back to the live coalescing
query** and log a warning — correctness preserved, assumption self-documenting.

---

## Phase A — read model (recommended to land first, as its own PR)

Built on the *current* priority tables so it delivers the perf win independently of B; B then
simplifies the build query under it (A's parity tests catch any drift).

1. **Model** — `db/model/og_field_resource_state.py`; export in `db/model/__init__.py` so
   Alembic autogenerate and `create_all` (tests) see it. Because it is a plain table, the
   `is_view` exclusion in `tests/conftest.py:144` is irrelevant.

2. **Build/refresh module** — `db/read_model/state.py`:
   - `compute_resource_state(session, resource_id) -> list[rows]` — for each of the 4 masks, run
     the existing coalescer restricted to that mask's visible sources. **Reuse**
     `coalesced_winner_rows` (queries.py:240) + `_view_and_provenance` (utils.py:36) — do **not**
     write a second coalescer, so the read model is defined by the same ranking the live path uses.
   - `refresh_resource_state(session, resource_id)` — delete + reinsert that resource's rows.
   - `remove_resource_state(session, resource_id)` — for merged-away resources.
   - `rebuild_all_resource_state(session)` — full rebuild (migration backfill + maintenance).

3. **Sync hooks** (same `UnitOfWork` transaction — `db/config.py:34`) in
   `db/og_field_resource_actions.py`: `create` (:326), `apply_resource_merge` (:357, refresh new
   target + `remove_resource_state` for each repointed original), `set_field_source_priority`
   (:234); and `attach_sources_to_resource` in `db/og_field_source_actions.py:199`.

4. **Read rewire** in `db/og_field_resource_actions.py`:
   - `query` (:57) — page/sort/filter over `og_field_resource_state WHERE permission_mask = ?`
     (typed columns), then project to `OGFieldListItemView` (values + jsonb provenance). Replaces
     `base_resource_query` + `coalesce_resources` on the fast path; keep the live path as fallback.
   - `filter_options` (:94) — `SELECT DISTINCT <field> ... WHERE permission_mask = ?` per
     `FILTER_OPTION_FIELDS`. This is the big win (indexed distinct vs full-table ranked scan).
   - Optionally serve `GET /{id}` view from the model. **`GET /{id}/detail` keeps the live
     `coalesced_candidate_rows` path** — `source_data` (all raw candidates) is not part of stored
     current-state, and detail is single-resource/cheap, not a perf target.

5. **Migration** — new revision (down_revision `71aa7ef8150b`): create table + `rebuild_all`
   backfill; irreversible `downgrade` per repo convention (e.g. `71aa7ef8150b`).

## Phase B — single priority store (second PR)

1. **Model** — `db/model/og_field_resource_attribute_priority.py`: `(resource_id, colname,
   source_pk)` PK, `priority` int, `is_curated` bool. Constraints: `UNIQUE(resource_id, colname,
   priority)`; `priority >= 0`; FK `(resource_id, source_pk)` → `og_field_memberships`; FK
   `(source_pk, colname)` → `oil_gas_field_source_values` (backed by existing
   `uq_source_value_colname`). Keep `colname` (string, closed `ATTRIBUTE_NAMES` set) — do **not**
   add `og_field_attributes` (that is scope C).

2. **Behavior-preserving priority column.** The single `priority` must linearize today's two-tier
   order exactly (`queries.py:_ranked`): curated rows first (contiguous 0..k−1), then default rows
   ordered by global `SOURCE_PRIORITY` rank with `source_pk` tiebreak, offset above the curated
   block. `is_curated` drives the `is_override` UI flag. New sources attached after curation append
   into the default block (design's sparse-rank guidance) so they rank last, matching current
   behavior.

3. **Rewrite ranking** — replace the two-column `override_priority NULLS LAST, default_priority,
   source, source_pk` window with `DISTINCT ON (resource_id, colname) ... ORDER BY priority` (or
   `rn=1` over `ORDER BY priority`) in `queries.py`. `field_source_candidates` returns
   `is_curated AS is_override`.

4. **Write paths write priority rows.** `create` / `attach_sources_to_resource` /
   `get_or_create_sources` seed default rows for every `(colname, source_pk)` value from
   `SOURCE_PRIORITY`. `set_field_source_priority` writes curated rows (`is_curated=True`) instead
   of the old override table. `apply_resource_merge` seeds defaults for the new target (overrides
   still intentionally not carried — actions.py:392).

5. **Migration** — create `og_field_resource_attribute_priority`, backfill from the two old tables
   + values + memberships, **drop** `og_field_source_priority` and `og_field_resource_source_priority`
   (design §4); irreversible downgrade. Update `tests/conftest.py:154` seeding to the new table.

## Files touched (representative)

- New: `db/model/og_field_resource_state.py`, `db/read_model/state.py`, `db/read_model/permissions.py`,
  `db/model/og_field_resource_attribute_priority.py`, two Alembic revisions.
- Modified: `db/queries.py`, `db/og_field_resource_actions.py`, `db/og_field_source_actions.py`,
  `db/model/__init__.py`, `tests/conftest.py`.
- Removed (Phase B): `db/model/og_field_source_priority.py`, `db/model/og_field_resource_source_priority.py`.

## Testing / verification

- **Parity tests** (new, `tests/db/`): seed a dataset spanning wm/ccr/public priorities; assert
  read-model `list` / `filter-options` / `GET /{id}` equal the live-coalesced results for all four
  permission profiles. Reuse builders in `tests/utils.py` / `tests/factories.py` and the
  `seeded_integration_session` / `integration_client` fixtures (`tests/conftest.py:186,197`).
- **Sync tests**: after create / attach / reprioritize / merge, assert stored rows == a fresh
  `rebuild_all_resource_state`.
- **Phase B ranking parity**: assert new single-table ranking reproduces `_ranked` output on the
  same fixtures (incl. curated-then-new-source and two-records-same-source cases).
- **Manual**: `make api-dev`; hit `/oil-gas-fields/`, `/oil-gas-fields/filter-options`,
  `/oil-gas-fields/{id}`; confirm `named_query` timings drop (observability context) and responses
  match `main`.
- `make check` before finishing.

## Risks / notes

- **Assumption dependency**: correctness of the 4-variant model rests on "only wm/ccr vary." The
  read-path fallback guards it; keep it and its warning.
- **B re-churns fresh STIT-494 code** (`a3f5c2e9b1d4`) and needs a data migration + drops — highest
  risk. Behavior-preservation is the acceptance bar; the parity tests are the safety net.
- **PR sequencing (recommended)**: land **A first** (perf win, low risk), then **B** — each is
  independently valuable and reviewable, per CONTRIBUTING (one concern per PR). B's table drops are
  an architectural change; flag for maintainer pre-approval before opening that PR.
- Per your global rule I will **not** commit or push — changes stay in the worktree working tree.
- Open (from the design, deferred): read-model row dedup/bitmask min-storage optimization;
  merge-time priority reset semantics if merge ever targets an existing resource.
