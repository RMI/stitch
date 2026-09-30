# STIT-763 — Filter options in one request and one query

**Status:** implemented on `feat/single-options-query`
**Ticket:** [STIT-763](https://rmi1.atlassian.net/browse/STIT-763) (epic STIT-689, "First real users!")
**Date:** 2026-09-15, revised 2026-09-16 to match what was built

---

## Problem

The Resource List page renders six filter dropdowns. Each one calls
`GET /oil-gas-fields/filter-options?field=X` on its own, so a page load fires six
requests. Every request rebuilds the full `active_src` join, ranks it, and takes a
`DISTINCT` over one value column.

Measured: about 1.6s per call, about 10.6s of database wall time per page load.

The waste is structural. `active_src` joins over the whole
`oil_gas_field_source_values` table (all 18 attributes) and the single-field
narrowing is applied *after* that join. So each of the six calls pays the full join
cost to use one field's worth of rows.

## Success criterion

A Resource List page load issues **one** filter-options request that runs **one**
database query.

Verified by the existing observability instrumentation (see
[`deployments/PERFORMANCE.md`](../../../deployments/PERFORMANCE.md)): the request
log for the route shows exactly one options query, and the route disappears as a
repeated entry in the query stream.

Measured on the local docker stack, 2026-09-16, with `LOG_ALL_QUERIES=true`:

```
QUERY     1.0ms rows=1     SELECT users.id, ... FROM users WHERE users.sub = ...
QUERY   181.1ms rows=1988  SELECT DISTINCT anon_1.colname, anon_1.value_text FROM ...
REQUEST db_query_count=2 db_time_ms=182.07
```

`db_query_count` reads **2**, not 1: the first query is the `get_current_user`
lookup that every authenticated route on this router pays, and is unrelated to
this change. The route's own database work is the single options query. The
browser makes one `/filter-options` request per page load, with no query string.

### Measured, 2026-09-15

Two runs against the local docker stack, at different data volumes, after ETL
runs for gem / wm / ccr / alb / bc plus 2,380 approved merges. Scripts in
`scripts/stit763_options_*.py`; `scripts/stit763_db_size.sql` for the volumes.

| Corpus | Current, 6 fields (the page load) | Current, 8 fields | **One query** | Page-load ratio |
|---|---|---|---|---|
| 6,227 resources, 44k filterable value rows | 62.7 ms | 84.9 ms | **27.6 ms** | 2.3x |
| 17,551 resources, 102k filterable value rows | 172.2 ms | 229.8 ms | **75.5 ms** | 2.3x |

**The ratio is stable at 2.3x across a 2.8x increase in data** (3.0x like-for-like
on eight fields). That stability is the transferable result. The absolute numbers
are local-only.

It is not 6x, and that was expected: the single pass ranks ~52% of the active
value rows instead of one field's ~6%, so per-query cost rises while the call
count drops from 6 to 1. The saving is the five repeated joins, not the ranking.

Payload is 934 values across the eight fields, which confirms the no-parameters
decision: there is nothing here worth letting a client trim.

**Still much smaller than production.** The ticket measured ~1.6s per call; this
box does ~29 ms. If the 2.3x ratio holds, one query in production turns a ~10.6s
page load into roughly 4-5s: a real improvement, but still slow enough that the
caching follow-up in [Out of scope](#out-of-scope) stays on the table. Do not
read 75 ms as the production number.

#### What the diff has confirmed

`stit763_options_baseline.py` diffs the one-query result against the current
per-field `filter_options`, value by value, calling both directly against a
session (no HTTP). **Identical** over a corpus that includes:

- all five sources present (gem 7,673, wm 5,050, ccr 1,321, alb 894, bc 233)
- 5,811 repointed (merged-away) resources
- 2,380 live resources holding 2+ active sources, so fields have real competition
- 24,054 curator override rows across 8,823 curated (resource, field) pairs
- 9,360 live single-source resources

**Licence parity.** `wm` and `ccr` are the only licensed sources; read access to
`bc`, `alb`, `gem`, `llm`, `rmi` is universal. So a user holds one of four source
sets, and the spike matches the current implementation for every one:

| Profile | Options returned | Spike vs current |
|---|---|---|
| open, no licence | 473 | identical |
| open + wm | 719 | identical |
| open + ccr | 756 | identical |
| open + wm + ccr | 933 | identical |

All four profiles return **different** answers (4 distinct of 4), so the parity
result is not vacuous: licensing genuinely changes which value wins a field, not
merely which rows are visible. `primary_hydrocarbon_group`, for instance, returns
10 values unlicensed and 11 with either licence. `licensed_sources=None` and the
explicit seven-source set were separately confirmed equivalent in both
implementations.

The script reports a warning if the profiles ever stop differing, since parity
would then prove nothing.

**The repointing invariant holds on real merged data**: 0 ACTIVE memberships sit
on a repointed resource, which is what makes dropping the `og_field_resources`
join safe.

Two findings the diff produced that reading the code did not:

1. **The `source, source_pk` tiebreak in the ranking window is load-bearing.** An
   early version of the spike omitted it and silently dropped a value: one
   resource held two ACTIVE records from the *same* source, which tie on
   `p.priority` (unique per source) and, with no override row, tie in the override
   tier too. Postgres then picked arbitrarily. Without that tiebreak the endpoint
   can return a different value set on identical calls.
2. **Enum coverage is complete once licensed.** All 4 `field_status`, all 4
   `production_conventionality`, 3 `location_type`, all 11
   `primary_hydrocarbon_group`. The dead-end-option risk behind the data-derived
   decision is real but currently empty at full licence.

#### Residual gap

One simplification is still untested by the diff: dropping production's
`o.source = m.source` term from the override join. That term guards against an
override row whose `(source, source_pk)` pair is mismatched, and this corpus
contains no such row (verified: 0). The join cannot fan out regardless, since the
remaining three columns are the override table's full primary key, so the only
exposure is a corrupt override row. Keep the term when this graduates to
production code.

**Resolved:** the shipped `filter_option_rows` keeps `o.source = m.source`.

## Decisions

| Question | Decision |
| --- | --- |
| Performance target | One query. Accept roughly one call's latency, re-measure, follow up separately if needed. |
| Request shape | No query parameters. The endpoint returns every supported field. |
| Supported fields | **Six**, matching what the UI renders. `name` and `name_local` are near-unique per resource and were never used by a dropdown; `location_type` and `production_conventionality` have no dropdown either, so they are not returned. |
| Contract change | Replace in place. Same path, new response shape. `field` and the already-ignored `source` param are both removed. |
| Statement construction | **Self-contained** in `queries.py`, not built on `construct_base_query_statement`. See [One query](#one-query). |
| Enum-backed fields | Options come from the data, not the type definition, so every offered value returns at least one row. |
| Frontend cache | Unchanged at 60s (`DEFAULT_STALE_TIME`). |
| Response model | Explicit Pydantic model with six declared fields, so OpenAPI and `API_REFERENCE.md` name every key. |
| `ValueKind.TEXT` guard | **None.** No import-time check, no test, no comment. The risk is real but small and cheap to fix later; see [The one-column shortcut](#the-one-column-shortcut). |
| Missing permission | **Not in this change.** `require_permissions(RESOURCE_READ)` is a separate ticket. |

## API contract

### Before

```
GET /oil-gas-fields/filter-options?field=country&source=gem

200
{ "field": "country", "values": ["CAN", "USA"] }
```

`field` was required. `source` was accepted and silently ignored. No permission
dependency on the route.

### After

```
GET /oil-gas-fields/filter-options

200
{
  "basin":                     ["Bakken", "Permian", ...],
  "country":                   ["CAN", "USA", ...],
  "field_status":              ["Abandoned", "Producing"],
  "primary_hydrocarbon_group": ["Dry Gas", "Light Oil", ...],
  "region":                    ["North America", ...],
  "state_province":            ["Alberta", "Texas", ...]
}
```

Contract details:

- **All six keys are always present.** A field with no licensed values is `[]`,
  never absent. The client never has to distinguish "no options" from "not returned".
- **Values are sorted** by raw stored value, ascending, and are never null or empty.
- **Licensing applies**, as it does today: the winner is chosen among licensed
  sources only, so a value present only in an unlicensed source is not offered.
- **Inactive memberships are excluded**, as today. Repointed resources are excluded
  by the same predicate rather than by their own; see
  [Accepted risk](#accepted-risk).
- No permission dependency, unchanged. Adding `resource:read` is a separate ticket.

## Backend design

### One query

The existing ranking window already partitions by `(resource_id, colname)`, so it
computes per-field winners for every field at once. The per-field narrowing is an
input filter, not a ranking requirement. Removing it and selecting `colname`
alongside the value gives all six fields from a single pass.

**The statement is self-contained**, not built on `construct_base_query_statement`.
That was the original recommendation and it was overruled in favour of leaner SQL.
This query reads `value_text` and the ranking keys only, so building it directly
skips that CTE's joins to `og_field_resources` and `oil_gas_field_sources` and its
unused typed value columns. Two joins the shared CTE performs are therefore absent:

- **`oil_gas_field_sources`.** `membership.source_pk` carries
  `ForeignKey("oil_gas_field_sources.id")`, so the identity half of that join can
  never drop a row; only `s.source = m.source` was doing work, and nothing selects
  from `s`.
- **`og_field_resources`.** Dropping it also drops `repointed_id IS NULL`. That is
  an accepted risk resting on a stated invariant; see
  [Accepted risk](#accepted-risk).

The cost is that the ranking logic now exists in two places (`_ranked` and
`filter_option_rows`) and the two must be kept in step by hand.

```sql
WITH ranked_src AS (
    -- membership -> values -> default priority,
    -- plus the per-value priority override outer join
    ...
    WHERE m.status = 'ACTIVE'
      AND m.source IN (:licensed_sources)
      AND v.colname IN (:filterable_fields)
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY resource_id, colname
        ORDER BY override_priority ASC NULLS LAST,
                 default_priority  ASC,
                 source            ASC,
                 source_pk         ASC
    ) AS rn
    FROM ranked_src
)
SELECT DISTINCT colname, value_text
FROM ranked
WHERE rn = 1
  AND value_text IS NOT NULL
ORDER BY colname, value_text;
```

**The `colname` narrowing is new and deliberate.** It shrinks the join and the
window-sort input to the six fields we actually need, instead of all eighteen
attributes, following the same rationale as the existing `resource_ids` parameter
on `construct_base_query_statement`: narrow before ranking so the window covers
only what is needed.

`value_text IS NOT NULL` is kept. Production has it today and removing it would be
an unrequested behavior change. It is defensive: the write path skips empty and
null values and `ck_source_value_text_nonempty` rejects empty text, so no row
reaches the filter with a null or empty `value_text`.

Result set size is the total number of distinct options across six low-cardinality
fields — small.

### The one-column shortcut

The query reads `value_text` and nothing else. That works because all six
filterable fields are `ValueKind.TEXT` in `ATTRIBUTE_KINDS`, so one physical column
serves every one of them: no `CASE` over typed columns, no per-field casting.

It also introduces the one genuinely new failure mode in this change. The old
per-field query called `value_attr_for(field)` and so always read the right column
for the field it was asked about. This one does not. Because the response model is
the source of truth for the query's `colnames`, adding a non-text field to that model
(say `discovery_year`, an `INT` living in `value_num`) would join that field's rows,
find `value_text` null on every one, drop them all at `value_text IS NOT NULL`, and
return `discovery_year: []`. No error anywhere. The dropdown would simply render
"No options."

**No guard was added.** An import-time `ValueKind.TEXT` check was considered and
rejected: the risk needs someone to add a non-text field to the response model, and
the symptom (an empty dropdown) is cheap to diagnose and fix. Add the guard if a
non-text field is ever proposed.

### Grouping the rows

Python groups the rows by `colname` into the response model by appending into a
dict pre-seeded with every field, which does not care what order the rows arrive in
and guarantees that a field with no rows still gets `[]`.

Avoid `itertools.groupby` here. It only groups *consecutive* equal keys, so it would
make the grouping silently dependent on the SQL `ORDER BY colname`: change or drop
that clause later and values get dropped rather than misfiled. The `ORDER BY` exists
to sort values *within* a field, which the "distinct and sorted" test covers. It
should not also be load-bearing for grouping.

Note what cannot go wrong: `colname` and `value_text` are two columns of the same row
of `oil_gas_field_source_values` and travel together through both CTEs, and `DISTINCT`
is over the pair rather than the bare value. So a value is always filed under the
label it arrived with, and a string that is a valid value for two different fields
(for example "Texas" as both a `state_province` and a `basin`) yields two rows and
lands correctly in both lists. Mixing values between fields would require separating
the label from the value first, which a pivot-shaped implementation
(`_add_pivot_columns`) or zipping independently-built lists would do. This design
does neither.

### Where the code lives

`queries.py` documents its own contract: "Construction is pure (no session);
execution + hydration live in `og_field_source_actions` /
`og_field_resource_actions`." Today's `filter_options` breaks that by assembling the
CTE chain inline in the actions module. This design follows the stated convention
rather than the current code.

| File | Change |
| --- | --- |
| `db/queries.py` | Add `filter_option_rows(licensed_sources)`, a self-contained select of distinct winning `(colname, value_text)` pairs. |
| `db/og_field_resource_actions.py` | `filter_options(session, licensed_sources)` executes that statement and groups rows. Signature loses the params object. The unreachable 422 check and `_FILTER_OPTION_FIELDS` go away with the `field` param, along with the now-orphaned `construct_base_query_statement`, `add_ranking` and `value_attr_for` imports. |
| `routers/oil_gas_fields.py` | Route takes no `params` and returns the action's response directly. No permission dependency added. |
| `entities.py` | `OGFieldFilterOptionsResponse` becomes the six-field model, with `FILTER_OPTION_FIELDS` derived from it. `OGFieldFilterOptionsParams` is deleted (nothing left to parse). The `FilterOptionField` Literal is deleted — this change orphans its only two uses. |
| `API_REFERENCE.md` | Regenerate via `deployments/api/scripts/api_doc.py`. |

The response model becomes the single source of truth for which fields are
filterable. The query derives its `colname` list from
`OGFieldFilterOptionsResponse.model_fields`, so the model and the query cannot drift.

```python
class OGFieldFilterOptionsResponse(BaseModel):
    basin: list[str]
    country: list[str]
    field_status: list[str]
    primary_hydrocarbon_group: list[str]
    region: list[str]
    state_province: list[str]


FILTER_OPTION_FIELDS: tuple[str, ...] = tuple(OGFieldFilterOptionsResponse.model_fields)
```

## Frontend design

`FilterBar` calls the hook once and passes each field's options down as a prop.

| File | Change |
| --- | --- |
| `queries/api.js` | `getResourceFilterOptions(config, fetcher, endpoint)` drops the `field` argument and the query string. |
| `queries/resources.js` | `keys.filterOptions(endpoint)` drops the field segment. The `[endpoint]` prefix is preserved, so mutation invalidation keeps working. |
| `hooks/useResources.js` | `useResourceFilterOptions(endpoint, enabled)` drops `field` and the `Boolean(field)` gate. The mock variant returns every `FILTER_FIELDS` key computed from mock data in one object. |
| `components/FilterBar.jsx` | One hook call at the top. `FilterFieldDropdown` existed only to make a per-field hook call, so its value-to-label mapping folds into the existing `FILTER_FIELDS.map` and the component goes away. |

The API's six fields and the UI's six dropdowns now match exactly. `FILTER_FIELDS`
stays the frontend's list of which dropdowns to render: the API's fields are what is
*available*, `FILTER_FIELDS` is what is *shown*. Adding a dropdown for a field the
API does not yet return (for example `location_type`) means adding it to
`OGFieldFilterOptionsResponse` as well.

`FilterDropdown.jsx` and `config/filters.js` need no change. The read shape changes
from `data?.values ?? []` to `data?.[key] ?? []`.

## Tests

Carry over the behaviors `TestResourceFilterOptionsAction` already pins, reading
one key off the response instead of a bare list:

- distinct and sorted
- null and empty values excluded
- licensing applied after coalescing
- inactive memberships excluded

The repointed-resource arm of the third test was **removed** and the test renamed to
`test_excludes_inactive_memberships`. This change drops the `repointed_id IS NULL`
predicate, so that half no longer tests anything real here; the `status = ACTIVE`
half still does. The list and detail paths keep their own repointing-exclusion
tests, which are unaffected.

Add:

- **All keys present.** Six keys in the response; a field with no data is `[]`.
- **Multi-field correctness in one pass.** Several fields populated at once, each
  returning its own values. Include the case where the same string is a legitimate
  value for two fields (for example "Texas" as both a `state_province` and a
  `basin`): both must appear, each under its own key. `DISTINCT` is over the
  `(colname, value)` pair, so this is what proves the pair, not the bare value, is
  what gets deduped.
Not added, both deliberately:

- **Every filterable field is text.** Dropped with the `ValueKind.TEXT` guard
  decision above.
- **Permission.** No permission dependency is added in this change.

Update or remove:

- Rewrite the Postgres-compile test to import and compile `filter_option_rows`
  directly. It previously hand-rebuilt the query and had already drifted from
  production, carrying an extra `!= ""` predicate production does not have.
- Delete `test_query_param_validation.py::test_invalid_filter_options_field_returns_422`.
  There is no `field` parameter left to validate.
- `test_resources_unit.py`: new response shape; drop the `source`-param test.
- Frontend: `ResourcesView.test.jsx` asserts one call instead of six per-field calls;
  `resources.test.js` key-prefix guard; `api.test.js` URL.

## Accepted risk

Dropping the `og_field_resources` join removes `repointed_id IS NULL` from this
query. Nothing at the schema level enforces the invariant it relied on: there is no
CHECK constraint or trigger, only an index. It is maintained by
`_repoint_memberships`, which flips old memberships to INACTIVE in the same
transaction that sets `repointed_id`. The baseline diff confirmed 0 ACTIVE
memberships on a repointed resource in the populated local database.

If that invariant is ever violated, a dropdown can offer a value that lives only on
a repointed resource. The list query still excludes repointed resources, so
selecting that option returns zero rows: a dead dropdown entry, not wrong data.

Enforcing the invariant as a database constraint is a candidate follow-up ticket.

## Out of scope

Deliberately excluded. Each is a separate ticket if measurement or product asks for it.

- **Caching or precomputation.** An in-process cache keyed by license set, or a
  refreshable table of distinct options, would take this well under 100ms. Both were
  considered and rejected for now: the one-query fix is far smaller, and a
  precomputed set has to be keyed by license set because the coalescing winner
  depends on which sources are licensed. Revisit only with a measurement showing one
  query is still too slow.
- **Longer frontend cache.** Raising `staleTime` for this one query would cut repeat
  fetches further, but it would make this query an exception to the app-wide default.
  Not worth mixing into this change.
- **HTTP `Cache-Control` headers.** The endpoint is auth-gated and
  licensing-dependent, so the header would have to be `private` and carefully scoped.
  Security-sensitive, and its own ticket.
- **Filter-dependent (cascading) options.** Options are global today and stay global.
  Making them reflect the active filter set would mean passing filter state in and
  recomputing per combination.
- **Facet counts.** `FilterDropdown` already destructures an unused `count` per
  option, so something once intended this. The same query could produce counts with a
  `COUNT(DISTINCT resource_id)` per `(colname, value)`, but it is not requested here.

## Surfaced, not fixed

Pre-existing issues found while reading. Flagged per the project convention rather
than changed.

- **Country dropdown sorts by ISO code, displays full names.** The API sorts by raw
  stored value and `FilterDropdown` renders options in the order received, while
  `FILTER_FIELDS` maps country codes to names via `getCountryName`. So the list reads
  "United Arab Emirates" (AE) before "Argentina" (AR). This change preserves that
  behavior. The fix is a frontend re-sort by display label.
- **Unused `count` in `FilterDropdown`.** Destructured per option and never rendered.
  Pre-existing dead code; left alone.
