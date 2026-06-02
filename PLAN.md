## Resource Filter Options Endpoint

### Summary
Add a read-only endpoint at `GET /oil-gas-fields/filter-options?field=country` that returns the distinct coalesced resource values visible to the current user for one requested field. The query must use the same resource-side coalescing and permission scoping as `GET /oil-gas-fields/`, but it will not apply the rest of the current list filters in this PR.

### Key Changes
- Add a new endpoint under the existing `oil_gas_fields` router:
  - `GET /oil-gas-fields/filter-options`
  - Required query param: `field`
- Define a small response model in the API entities layer.
  - Default assumption: `{ "field": "country", "values": ["CAN", "USA"] }`
  - Keep `values` sorted ascending and omit `null` / empty-string values.
- Add a dedicated field-param type for this endpoint rather than reusing `OGFieldQueryParams`.
  - Validate `field` against a whitelist of supported resource filter-option fields.
  - Default assumption: support the coalesced scalar filter fields used by the table filters, not `q`, not list/JSON fields (`owners`, `operators`), and not raw-source-only fields.
- Implement a new DB action on top of the existing coalesced resource CTE in `og_field_resource_actions.py`.
  - Reuse `_build_licensed_resource_list_cte(...)` so results match resource visibility and source-priority coalescing.
  - Do not apply `_build_final_conditions(...)` in this endpoint.
  - Do still pass `licensed_sources(claims)` and the selected `source` set, so the result reflects the user-visible resource universe.
- Keep this endpoint resource-based, not source-based.
  - Distinct values come from the coalesced resource columns after permission scoping, never from raw source rows.

### API / Behavior Details
- Request:
  - `GET /oil-gas-fields/filter-options?field=country`
  - Optional `source` query params may still be accepted if convenient, since source selection is part of resource visibility.
- Response:
  - `field`: echoed requested field
  - `values`: distinct visible values for that coalesced field
- Validation:
  - Unknown or unsupported `field` returns `422`.
- Non-goal for this PR:
  - No interaction with the rest of the active resource filters.
  - This means the UI may later allow choosing a filter value that produces an empty result set; that is accepted for now.

### Test Plan
- Router unit tests:
  - `GET /oil-gas-fields/filter-options?field=country` returns `200` and the expected response envelope.
  - Invalid field such as `owners` returns `422`.
  - Router passes claims-derived licensed sources into the DB action.
- DB integration tests:
  - Distinct values are computed from coalesced resource data, not individual source rows.
  - Licensed-source restrictions remove values that only exist in unlicensed sources.
  - Repointed / inactive-membership resources are excluded consistently with the main resource list.
  - `null` and empty-string values are excluded.
  - Results are sorted and deduplicated.

### Assumptions
- The endpoint should ignore current non-source resource filters in this PR, per your direction.
- The response should be a simple object with `field` and `values`.
- Supported `field` values should be limited to resource-table filter fields, not every `OilGasFieldBase` attribute.
