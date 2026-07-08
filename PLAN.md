# Per-field, per-source-record priority overrides (STIT-493 follow-up)

## Context

PR [#159](https://github.com/RMI/stitch/pull/159) added a read-only "All sources" panel that expands a
`FieldCard` to show every source's value for one field of a resource, winner-first
(`GET /oil-gas-fields/{id}/fields/{field}/sources`). It deliberately left a reserved
header ("future controls will live alongside this label") and no way to *change* which
source wins.

This change lets a curator (`resource:write`) reorder those sources **per field** and
persist the new order, so the coalesced value shown to everyone changes. The EAV
overrides table `og_field_resource_source_priority` already participates in the coalesce
query but (a) is keyed per-resource/per-source-**key** rather than per-field/per-source-**record**,
and (b) has no writer. This work makes the override per-`(resource, source_record, field)`
and adds the write path + edit-mode UI.

### Confirmed decisions
- **Scope:** per-field. Reordering *Basin* affects only *Basin*.
- **Granularity:** per source **record** (`source_pk`), so two records from the same
  source can be ranked independently. Fulfills the deferred item in
  `memory/per-source-record-priority-override.md` — update that memory note on completion.
- **Audit:** lightweight only — `created`/`updated`/`created_by_id`/`last_updated_by_id`
  via the existing mixins. No history table, no notes/previous-winner columns. See
  *Known limitation* below; revisit richer provenance later.
- **New sources sort last:** a record with no override row for a field must rank below
  every overridden record, regardless of its global-default priority.
- **Complete snapshot:** a save writes a priority row for *every* record that currently
  has a value for the field; persist only if the effective order actually changed.

## Target semantics (the invariant every layer preserves)

Effective ranking for a `(resource, field)`, best-first:
1. **Tier 0 — overridden records**, ordered by `override.priority ASC`.
2. **Tier 1 — non-overridden records**, ordered by `default.priority, source, source_pk`.

Realized in SQL as `ORDER BY override_priority ASC NULLS LAST, default_priority ASC, source, source_pk`
(override priority is `NOT NULL`, so `NULLS LAST` *is* the tier split). Realized in Python
as an explicit per-field sort key. This is why the old single `COALESCE(override, default)`
priority must split into two columns — a collapsed value can't express the tier.

## Backend changes

### 1. Migration — `deployments/api/alembic/versions/`
The override table is empty and has no writer, so **drop + recreate** (avoids a
cross-dialect PK-alter dance; baseline uses postgres+sqlite `with_variant`).
- New PK `(resource_id, source_pk, colname)`.
- Columns: `resource_id` (FK `og_field_resources.id` CASCADE), `source` (String(10), FK
  `og_field_source_priority.source` — **kept**, used as a ranking tiebreak and known-key
  guarantee), `source_pk` (FK `oil_gas_field_sources.id` CASCADE), `colname` (String(50),
  matching `oil_gas_field_source_values.colname`, with the same `CheckConstraint` on the
  known attribute names), `priority` (Integer), plus the four audit columns.
- `downgrade()` recreates the old shape. Run `make alembic-check` to confirm no drift.

### 2. Model — `.../db/model/og_field_resource_source_priority.py`
Add `source_pk`, `colname`; mix in `TimestampMixin, UserAuditMixin`; set the new PK; add a
`create(*, created_by, resource_id, source, source_pk, colname, priority)` classmethod
mirroring `ResourceModel.create` / `MembershipModel.create`.

### 3. SQL coalesce — `.../db/queries.py`
- `construct_base_query_statement`: change the override outer join to the value grain —
  `and_(o.resource_id == r.id, o.source_pk == m.source_pk, o.colname == v.colname)` (same
  `(source_pk, colname)` grain as `v`, so **no fan-out**). Emit **two** columns instead of
  the collapsed `priority`: `override_priority = o.priority` (nullable) and
  `default_priority = p.priority`.
- `add_ranking`: order by `override_priority.asc().nulls_last(), default_priority.asc(),
  source.asc(), source_pk.asc()`; partition unchanged `(resource_id, colname)` → still one
  winner per `(resource, field)`.
- Filter/sort/`filter_options` don't read priority, so they're unaffected beyond the column
  rename. Grep for any other reader of `active_src.c.priority` before removing it.

### 4. Python coalesce — `coalesce.py`, `db/utils.py`, `db/model/resource.py`
- `coalesce_og_field_resource(source_data, priorities=SRC_PRIORITY, *, field_overrides=None)`
  where `field_overrides: Mapping[str, Mapping[int, int]]` is `field → {source_pk → raw
  override_priority}`. `None`/empty ⇒ today's behavior (backward compatible; the
  `resource_to_view`/`resource_to_list_item_view` default-arg callers keep working).
  Replace the single reverse-sort-and-reduce with a **per-field argmin** (Option A): for
  each field independently, pick the record with the smallest tiered sort key among records
  whose value is non-null. Tier computed *inside* the coalescer from raw override priorities.
- `ResourceModel.field_overrides_by_resource_id(session, resource_ids) ->
  dict[int, dict[str, dict[int, int]]]`: one query over the override table (no joins), not
  licensing-filtered (overrides for unloaded records are inert).
- `ResourceModel.source_data_by_resource_id`: drop the now-invalid `outerjoin(o, ...source==...source)`;
  return `(entity, default_source_priority)` from `p.priority` only.
- `coalesce_resources`: load overrides alongside sources (one extra batched query per page)
  and pass `field_overrides=overrides_by_id.get(rid)` into the coalescer.

### 5. Read endpoint action — `field_source_values` in `og_field_resource_actions.py`
Make it field-aware: load the field's overrides, sort candidates by the same tiered key.
Set `OGFieldSourceValueView.priority` to the effective per-field priority, but note that
with tiering the int is no longer a cross-record total order — **consumers must rely on
list order** (already winner-first). Optionally add an `is_override: bool` to the view if
the FE needs it; not required for correctness.

### 6. Write path
- Action `set_field_source_priority(session, user, resource_id, field, ordered_source_pks,
  licensed_sources) -> list[OGFieldSourceValueView]`. Validation, cheapest first:
  field in `ATTRIBUTE_NAMES` (422); resource exists & not repointed (404 / `ResourceIntegrityError`
  400); no duplicate pks (400); the request must cover **exactly** the eligible set (active
  members with a non-null/non-empty value for the field, computed via the same logic as
  `field_source_values`, licensed only) — missing or extra pks → `InvalidActionError` (400).
- **No-op:** compute current effective order over the eligible set; if it equals
  `ordered_source_pks`, return early without writing.
- **Persist:** delete all rows for `(resource_id, colname=field)`, then insert one row per
  pk with `priority = enumerate index` (0-based; lower = better; only ever compared within
  tier 0). Set audit columns via `create`. `flush()` only — UoW commits on clean exit.
- Router: `PUT /{id}/fields/{field}/sources/priority`, `dependencies=[Depends(require_permissions(RESOURCE_WRITE))]`,
  body `SetFieldPriorityRequest(ordered_source_pks: list[int])` (add to `stitch.api.entities`).
  Same try/except as merge endpoints (400/404/re-raise HTTPException). Pass
  `licensed_sources(claims)`. Reuse the existing route-permission test matrix in
  `tests/routers/test_route_permissions.py`.

### Behavior alignment to decide during implementation
`field_source_values` filters `value != ""`, but the coalescer currently only skips `None`
(so `""` can win the coalesced view) — the two **disagree today**. Align the coalescer to
also skip `""` so the "All sources" winner matches the displayed value; cover with a test.

## Frontend changes (`deployments/stitch-frontend/`)

- **Permission hook:** none exists today (only `ColophonPanel` reads `authMe.claims.permissions`
  from `/health/details`). Add a small `useHasPermission("resource:write")` hook reading the
  same claims, and gate the Edit affordance on it.
- **Edit mode** in `components/ResourceFieldCard.jsx` (`FieldSourcesPanel`): add an **Edit**
  button inline with the "All sources" header (the reserved header). Edit mode makes the rows
  reorderable via **up/down move buttons** (no new dependency; accessible — dnd-kit is a
  possible future upgrade). Track the working order in local state seeded from the fetched
  list; a **Save** button (reuse `components/Button.jsx`) is disabled until the working order
  differs from the original.
- **Save call:** add `updateFieldSourcePriority(config, id, field, orderedSourcePks, fetcher,
  endpoint)` to `queries/api.js` (PUT, body `{ ordered_source_pks }`), called with the
  established async/try-catch + `useState` pattern (the codebase doesn't use `useMutation`).
  On success, invalidate the `fieldSources` query key and the resource-detail query so the
  winner and the collapsed value refresh. Add a matching mock branch in
  `hooks/useResources.js` (mirroring `useFieldSourceValuesMock`).
- Update `ResourceFieldCard.test.jsx` for edit mode (open → Edit → reorder → Save enabled →
  Save calls the mutation) and the no-permission case (no Edit button).

## New-source behavior (documented + tested)
Because a save writes a row for every record that has a value, a record added *later* has no
override row and lands in tier 1 (last), ordered by default priority — matching "new sources
at the lowest position." A record that later *gains* a value it didn't have at save time also
lands in tier 1. Cover both in tests and note in the endpoint/docstring.

## Known limitation (audit)
Delete-and-reinsert + lightweight columns capture only who/when for the *current* ordering;
prior winners are not retained, so "infer previous state from previous changes" is not
possible from this table alone. This is the accepted trade-off for now; a future append-only
history table (declined here) would enable it. Record this in the docstring and the memory
note.

## Verification
- `make py-test` (or `make api-test` for the API package) — new tests:
  - **Coalescer (pure):** per-field isolation (reorder basin, name unchanged); new source
    sorts last despite better default; two same-source records with one overridden;
    `field_overrides=None` byte-identical to pre-refactor (golden); `""` semantics.
  - **Query/DB:** `add_ranking` picks the override winner per `(resource, colname)`;
    unlicensed source excluded even with an override row; list filter/sort/`filter_options`
    regression; FK CASCADE removes override rows when a source record is deleted.
  - **Write path:** no-op save writes nothing; reorder rewrites rows and flips the coalesced
    winner; incomplete/extra/duplicate pk → 400; repointed → 400/404; unknown field → 422;
    missing `resource:write` → 403; global-default change leaves overridden field unaffected.
- `make frontend-test` — edit-mode component tests above.
- `make alembic-check` — migration matches models.
- `make check` — full lint/format/test/lock gate before finishing.
- Manual: `make api-dev` + frontend; open a resource detail with the seeded
  `006-source-values-demo` data (multiple GEM records), expand a field, reorder, save,
  reload, confirm the winner changed and persisted.

## Critical files
- `deployments/api/src/stitch/api/coalesce.py`
- `deployments/api/src/stitch/api/db/queries.py`
- `deployments/api/src/stitch/api/db/model/resource.py`
- `deployments/api/src/stitch/api/db/model/og_field_resource_source_priority.py`
- `deployments/api/src/stitch/api/db/utils.py`
- `deployments/api/src/stitch/api/db/og_field_resource_actions.py`
- `deployments/api/src/stitch/api/routers/oil_gas_fields.py`
- `deployments/api/alembic/versions/` (new revision)
- `deployments/stitch-frontend/src/components/ResourceFieldCard.jsx`
- `deployments/stitch-frontend/src/hooks/useResources.js`, `src/queries/api.js`, `src/queries/resources.js`
