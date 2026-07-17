# SQL-authoritative source coalescing

## Context

Source coalescing (pick the highest-priority non-empty value per field, per resource,
plus provenance) is currently implemented **twice** and the list endpoint does the work
**twice per request**:

- **SQL** (`db/queries.py` — `construct_base_query_statement` + `add_ranking`): a
  `coalesce(override, default)` join, a `row_number()` window over
  `(resource_id, colname)`, and a `max(case ...)` pivot. Used **only** to find which
  resource IDs match a filter/sort and for `filter-options`. It computes the winning
  values and then throws them away.
- **Python** (`api/coalesce.py` — `coalesce_og_field_resource`, orchestrated by
  `db/utils.py::coalesce_resources`): a sort-by-priority + reduce that produces the actual
  values + provenance returned to clients. This is the real value-builder behind the list
  (phase 2), detail (`GET /{id}`, `GET /{id}/detail`), create, and merge.

The list path (`db/og_field_resource_actions.py::query`) runs the SQL coalesce to get a
page of IDs (phase 1), then **re-fetches those same rows and re-coalesces them in Python**
(phase 2). The two implementations must agree by hand, and already **don't**: e.g.
`field_source_values` skips `value == ""` but the Python coalescer only skips `None`, so an
empty string can win the coalesced view while being hidden from the "all sources" list.
Merge-preview uses a *third*, defaults-only priority ordering. Per `deployments/PERFORMANCE.md`,
the phase-1 coalesce CTE is the documented hot path (~9× latency growth 1k→50k rows).

**Goal:** make **SQL the single authoritative place coalescing happens**. Python's only job
becomes boundary work — validate inputs before write, and materialize/validate the wide
coalesced row into the pydantic entity after read. This kills the SQL-vs-Python drift on the
hot paths, collapses the list to a single query, and leaves exactly one CTE to optimize when
the scaling work happens later.

Because merge-preview is the *only* remaining caller of the Python coalescer, this change
**removes merge-preview** (temporarily) so `coalesce_og_field_resource` and all Python-side
coalescing can be **deleted outright** rather than kept on life-support. Preview will be
reintroduced with the separate merge rework.

**Explicitly out of scope** (confirmed with the requester):
- **Field-level reprioritization (PR #164)** — a separate, later PR. This change stays on
  today's **source-level** priority (`coalesce(override, default)` keyed on
  `(resource_id, source)`), leaving the two-tier `ORDER BY` for that PR to add by editing one
  place.
- **Merge apply/review** (`apply_resource_merge`, the review page's approve/reject flow) —
  unchanged. Only the merge *preview* is removed; applying a merge still works and now
  hydrates its result via the SQL coalesce like every other read.

## Success criteria (what would prove this is done)

1. `GET /api/v1/oil-gas-fields/` (list) is served by **one** coalescing query — no phase-2
   Python re-coalesce. Response bytes are unchanged for existing data (golden test).
2. `GET /{id}` and `GET /{id}/detail` get their coalesced values + provenance from the same
   SQL coalesce (narrowed to one id), not from `coalesce_og_field_resource`.
3. `coalesce_og_field_resource`, `SRC_PRIORITY`, and the rest of `api/coalesce.py` are
   **deleted** — zero callers remain. Merge-preview is removed and its component shows a
   "temporarily unavailable" message.
4. Empty-string values never win the coalesced view (aligns the previously-disagreeing SQL
   and Python behaviors); covered by a test.
5. Priority ordering is expressed in SQL only — including the `field_source_values`
   "all-sources" ordering (no Python `.sort` on priority).
6. `make check` (lint/format/test/lock) passes; list/detail/filter-options behavior is
   otherwise unchanged.

## Approach (recommended: full SQL-authoritative funnel)

### 1. Extend the SQL coalesce to *return* values + provenance
`db/queries.py`:
- In `add_ranking`, filter the ranking input so empty text loses:
  drop rows where `value_text IS NOT NULL AND value_text = ''`. The
  `ck_source_value_exactly_one` invariant guarantees only text-kind attributes populate
  `value_text`, so this is type-correct and touches nothing numeric/JSON. This is the single
  fix for success-criterion 4.
- Extend `_add_pivot_columns` (or add a sibling) so each participating field pivots **three**
  columns — its typed value (`value_attr_for(field)`), its winning `source`, and its winning
  `source_pk` — off the `rn == 1` row. Value + provenance now come straight from the query.
- Add a builder that returns the full coalesced wide row for a set of resource IDs (all
  attributes in `ATTRIBUTE_NAMES`, not just participating ones), reusing
  `construct_base_query_statement` + `add_ranking`. This is what both list and detail hydrate
  from. `base_resource_query` keeps its narrowed-pivot form for the *filter/sort/paginate* id
  selection; the new builder produces the *values* for the resolved page (or single id).

### 2. Hydrate the pydantic entity from the wide row (Python = boundary only)
`db/utils.py`:
- Replace `coalesce_resources`' internals: instead of `source_data_by_resource_id` + the
  Python reduce, run the SQL coalesce wide-row query and build each `OGFieldResource` from the
  row using the existing `materialize_value(colname, value_text, value_num, value_json)`
  ([db/model/oil_gas_field_source_value.py](deployments/api/src/stitch/api/db/model/oil_gas_field_source_value.py))
  for typing/JSON, and read the winning `source` columns into the provenance dict. No priority
  logic in Python.
- Delete the `force_coalesce` / `view is None` fallbacks in `resource_to_view` /
  `resource_to_list_item_view` (grep confirmed `force_coalesce=True` is never passed): the
  entity always carries the SQL-computed view/provenance, so these become pure projections.
- Detail still needs the **raw** source list (`OGFieldDetailView.source_data`) and
  `constituents` / `repointed_to`. Keep `source_data_by_resource_id` as the raw-source fetch
  (its `priority` column is no longer used for coalescing but may still feed
  `field_source_values` display) plus the existing constituent/repoint lookups.

### 3. List path → single-phase
`db/og_field_resource_actions.py::query`:
- Keep phase 1 (`base_resource_query` → count + page of ids in sort order).
- Replace phase 2: hydrate the page from the new wide-row query (step 1) rather than
  `coalesce_resources` + `resource_to_list_item_view`'s reduce. Preserve phase-1 ordering by
  indexing the wide rows by id. (If a combined single-statement id+values query proves clean,
  it can subsume phase 1 too — but keeping the id-select for count/pagination is the low-risk
  default.)

### 4. Move all-sources ordering into SQL
`db/og_field_resource_actions.py::field_source_values`: replace the Python
`values.sort(key=lambda v: (v.priority, v.id))` with an `ORDER BY` in the query using the same
ordering expression as `add_ranking`, so tier/priority ordering lives in exactly one place.

### 5. Remove merge-preview and delete the Python coalescer
Merge-preview is the last caller of `coalesce_og_field_resource`. Remove it so the module can go.
- **Backend:** delete `preview_merge_candidate` (`db/merge_candidate_actions.py:230-283`), the
  `GET /merge-candidates/{id}/preview` route (`routers/oil_gas_fields.py:123-147`), and the now
  unused `OGFieldMergePreviewView` (`entities.py:175`). Remove their tests.
- **Frontend:** in `MergeCandidateReviewPage.jsx`, change `PreviewPanel` to render a short
  "Merge preview is temporarily unavailable" message and **stop firing the preview query**
  (drop the `useMergeCandidatePreview` call and its wiring). Leave the approve/reject-with-notes
  flow untouched. Remove the now-dead `getMergeCandidatePreview` (`queries/api.js`),
  `mergeCandidatePreview` / `preview` key (`queries/resources.js`), and the
  `useMergeCandidatePreview*` hooks (`hooks/useResources.js`) — or keep them if trimming widens
  the diff more than it's worth; the load-bearing change is that the component no longer calls
  the endpoint.
- **Delete `api/coalesce.py`** (`coalesce_og_field_resource`, `SRC_PRIORITY`, `ProvAttrs`) once
  the grep for its symbols comes back empty.

### Files
- `deployments/api/src/stitch/api/db/queries.py` (ranking empty-filter, provenance pivot, wide-row builder)
- `deployments/api/src/stitch/api/db/utils.py` (`coalesce_resources` → SQL hydration; drop force_coalesce branches)
- `deployments/api/src/stitch/api/db/og_field_resource_actions.py` (`query` single-phase; `field_source_values` SQL ordering)
- `deployments/api/src/stitch/api/db/model/resource.py` (`source_data_by_resource_id` — keep as raw fetch; drop coalesce-only concerns)
- `deployments/api/src/stitch/api/db/merge_candidate_actions.py`, `routers/oil_gas_fields.py`, `entities.py` (remove preview action/route/view)
- `deployments/api/src/stitch/api/coalesce.py` — **deleted**
- `deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx` (+ `queries/api.js`, `queries/resources.js`, `hooks/useResources.js`) — preview → "temporarily unavailable"

## Alternative considered (scope-down fallback)

**List single-phase only; keep Python for detail/create.** Smaller and safer — de-dupes the
list's *internal* double work — but list and detail would still use different coalescers, so
the SQL-vs-Python drift (and the `""` bug class) survives on the detail path, and
`coalesce_og_field_resource` keeps four callers. It buys the modest list-latency trim without
the maintainability win that motivated this. Recommend the full funnel; fall back to this only
if the detail-path change proves riskier than expected under review.

## Risks / tradeoffs

- **Denser query.** The wide coalesced row is ~3 columns × up to 18 fields, and debugging
  "why did source X win field Y" moves from a Python reduce to a window+pivot. Mitigated by
  the pivot being *generated* (not hand-written) and by one authoritative definition replacing
  the current guess-which-coalescer. This is the main tension vs. `AGENTS.md`'s clarity
  principle — accepted because the duplication has already shipped a real bug.
- **Detail now runs the ranking CTE** (scoped to one `resource_id`, so a tiny partition) where
  it previously coalesced in memory. Cheap, but a different query plan — measure it.
- **Intentional behavior change:** empty strings stop winning the coalesced value. Verify no
  consumer relied on the old behavior.
- **Merge preview is temporarily removed** — a deliberate UX regression. Approve/reject still
  work; only the pre-merge preview is gone, to be restored with the merge rework. This also
  retires the third (defaults-only) priority path, so nothing coalesces in Python anymore.

## Verification

- **Tests** (`make api-test`):
  - Golden: list + detail responses byte-identical to pre-change for seeded data.
  - Empty-string: a higher-priority source with `""` for a field loses to a lower-priority
    non-empty source, in both the coalesced value and `field_source_values` order.
  - Provenance: winning source per field matches the pre-change Python provenance.
  - Null-shell: a resource whose only values are unlicensed/absent still lists as all-None and
    drops out under a field filter (existing behavior preserved).
  - `api/coalesce.py` is deleted and `grep -rn coalesce_og_field_resource\|SRC_PRIORITY` over the
    source tree returns nothing.
  - Merge-preview endpoint is removed; merge apply/review tests still pass.
- **Frontend** (`make frontend-test`): `MergeCandidateReviewPage` shows the "temporarily
  unavailable" message, issues no preview request, and approve/reject still works.
- **Otel / perf** (merge the observability branch first): drive the list per
  `deployments/PERFORMANCE.md`, confirm `db_query_count` per list request drops (phase-2 fetch
  gone) and the coalesce CTE is still the dominant statement — establishing the clean baseline
  for the later scaling work. `EXPLAIN (ANALYZE, BUFFERS)` the new wide-row query at ~50k rows.
- **Manual** (`make api-dev` + frontend): open the seeded `006-source-values-demo` resource,
  confirm list, detail, and the "all sources" panel show identical winners/values before and
  after.
