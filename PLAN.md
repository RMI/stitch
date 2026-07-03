# See source values per field (Resource Detail)

## Context

On the Resource Detail page, each field currently shows only the **coalesced/winning**
value with a source-colored left border ([FieldCard.jsx](deployments/stitch-frontend/src/components/FieldCard.jsx)).
Users can't see the competing values from other sources without scrolling to the
separate **Sources** section (which is organized by source, not by field).

This feature makes a field value clickable to reveal an **inline "All sources" panel**
listing every source record that has a value for that field — the winner highlighted,
the rest diminished and shown in priority order. This satisfies the Jira AC:
per-field source/value/row-ID visibility, color-coding, winner marking, and clean
handling of empty values — with no raw JSON.

Key discovery from exploration: the resource-detail response **already carries all the
data we need in memory** — `detailView.source_data` holds every source record with its
per-field values and `source.id` (source row ID), and `detailView.provenance[field]`
already names the winning source. **No new frontend query or lazy-load is needed for
the core feature.** The only backend change is exposing the effective per-resource
source **priority** so the losing rows can be ordered correctly (respecting overrides).

Decisions confirmed with the user:
- **Row content:** color bar + source label + value + **source row ID**. Zero extra
  queries. Import date / producer are explicitly **deferred** to a follow-up (they
  require the per-source lazy endpoint and already live in the Sources section).
- **Interaction:** inline expand beneath the clicked field.
- **Ordering:** expose real priority from the backend (do **not** approximate on the
  frontend), mindful of the EAV source-value construction.

---

## Backend — expose effective source priority

The effective per-resource priority (`COALESCE(override, default)`) is **already computed**
in `coalesce_resources` but discarded ([utils.py:87-88](deployments/api/src/stitch/api/db/utils.py:87)):
`prio_map = {src.source: prio ...}`. We just need to carry it to the detail view.

Note on EAV: source **values** now live in the long/EAV table
`oil_gas_field_source_values` ([oil_gas_field_source_value.py](deployments/api/src/stitch/api/db/model/oil_gas_field_source_value.py)),
but **priority** comes from the `og_field_source_priority` / `og_field_resource_source_priority`
tables — this change does not touch EAV. Source values reach the frontend already
materialized on each `OGFieldSourceView`, so the panel reads `record[field]` as today.

1. **Entity** — add a field to `OGFieldResource` in
   [packages/stitch-ogsi/.../model/__init__.py:118](packages/stitch-ogsi/src/stitch/ogsi/model/__init__.py:118):
   `source_priority: dict[OGSISrcKey, int] = Field(default_factory=dict)`
   (lower int = higher priority).

2. **Populate it** in `coalesce_resources`
   ([utils.py:91](deployments/api/src/stitch/api/db/utils.py:91)): pass the existing
   `prio_map` into the `OGFieldResource(...)` construction as `source_priority=prio_map`.

3. **View** — add `source_priority: dict[OGSISrcKey, int]` to `OGFieldDetailView`
   ([model/__init__.py:104](packages/stitch-ogsi/src/stitch/ogsi/model/__init__.py:104))
   and set it in `resource_to_detail_view`
   ([utils.py:142](deployments/api/src/stitch/api/db/utils.py:142)) from
   `resource.source_priority`. Leave `OGFieldListItemView` untouched (keeps list
   payloads lean; detail-only).

`provenance[field]` (winning source key) and `data[field]` (winning value) already flow
to the client and are enough to mark the winner — no change to `provenance` shape (avoids
breaking `FieldCard`'s current `source` prop).

---

## Frontend — clickable field + inline "All sources" panel

### 1. New selector util — [utils/resourceDisplay.js](deployments/stitch-frontend/src/utils/resourceDisplay.js)
`getFieldSources(detailView, fieldKey)` → array of `{ id, source, value, isWinner }`:
- Iterate `detailView.source_data`; include a record only when `record[fieldKey]` is
  non-null / non-empty (empty-handling AC — no clutter).
- `isWinner = record.source === detailView.provenance[fieldKey] && record[fieldKey] === detailView.data[fieldKey]`.
- Sort: winners first, then ascending by `detailView.source_priority[source]`
  (best-first), tiebreak by `id`. Fall back gracefully if `source_priority` is missing.
- Scope to primitive fields (identity + production); owners/operators (JSON arrays)
  are out of scope and won't be passed this prop.

### 2. `FieldCard` gains an optional expandable panel — [components/FieldCard.jsx](deployments/stitch-frontend/src/components/FieldCard.jsx)
- Add optional prop `sources` (the `getFieldSources` array). When present and non-empty,
  render the value box as a `<button>` toggle (`aria-expanded` / `aria-controls`,
  focus-visible ring) that reveals an inline panel **below the card**, following the
  existing expand idiom in `SourceRow` / `TechnicalImportRecord`
  ([ResourceDetailPage.jsx:374-505](deployments/stitch-frontend/src/pages/ResourceDetailPage.jsx:374)).
- When `sources` is absent/empty, render exactly as today (keeps `OrgPanel`,
  `TechnicalImportRecord`, `SourceRow` usages unchanged and non-interactive).
- Panel structure (small subcomponents in the same file, e.g. `FieldSourcesPanel` +
  `SourceValueRow`):
  - **Reserved header** `All sources` (a `text-xs font-semibold uppercase tracking-wide
    text-ink-muted` label, room for future controls per the request).
  - One row per source record, one line: heavier colored left bar
    (`SOURCE_COLORS[source]`) + `SourceLabel:` + `"value"` + muted source row ID
    (`#<id>`). Reuse `SOURCE_COLORS` / `SOURCE_LABELS` from
    [constants/sourceMeta.js](deployments/stitch-frontend/src/constants/sourceMeta.js).
  - **Winner row** highlighted with the established light-grey `bg-surface` and a "Winner"
    marker; **non-winners** diminished (`text-ink-muted`).
- Layout note: the panel expands within the (narrow) grid cell; the one-line row format
  fits, long values wrap. Acceptable per the chosen inline approach.

### 3. Wire it up — [pages/ResourceDetailPage.jsx](deployments/stitch-frontend/src/pages/ResourceDetailPage.jsx:579)
In the Identity and Production `FieldGrid`s, pass
`sources={getFieldSources(detailView, key)}` to each `FieldCard` (alongside existing
`label` / `value` / `source`). Organizations section unchanged.

---

## Tests
- **Backend:** extend the coalesce/view tests to assert `source_priority` appears on the
  detail view and reflects a per-resource override (`api-test` area; there are existing
  tests around `resource_to_detail_view` / `coalesce_resources`). Run via `make api-test`
  / `make pkg-test-ogsi`.
- **Frontend:**
  - New `resourceDisplay.test.js`: `getFieldSources` — winner detection, empty-value
    exclusion, priority ordering, duplicate same-source records.
  - Extend [FieldCard.test.jsx](deployments/stitch-frontend/src/components/FieldCard.test.jsx):
    non-interactive without `sources`; clicking toggles the panel; winner row highlighted;
    rows in priority order; source row ID rendered. Use `userEvent` + existing RTL setup.

## Verification
1. `make check` (or `make frontend-test` + `make api-test` for the focused loop; `make
   frontend-lint` / `make py-lint`).
2. Run the frontend dev server, open a Resource Detail for a field with multiple sources
   (e.g. Basin), click the value: confirm the "All sources" panel opens inline, the
   Woodmac/winning value is highlighted with a light-grey background, others appear below
   in priority order with color bars + source row IDs, and clicking again collapses it.
3. Confirm a field with a per-resource priority override orders the losing rows by the
   override (validates the backend `source_priority` wiring).

## Deferred follow-ups
- Per-row **import date / producer** (needs the per-source lazy endpoint
  `useSourceDetail` → `/oil-gas-field-sources/{id}/detail`; N requests per open panel).
- Additional controls in the reserved **All sources** header (future functionality the
  user mentioned).
