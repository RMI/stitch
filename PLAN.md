# Expand `GET /oil-gas-fields/merge-candidates/{id}` response model

## Context

The merge-review flow is being reworked (eventually toward unified "source management" — merge vs. attach-source becoming an internal distinction the user doesn't see). As a leadup, the detail endpoint for a single merge candidate needs to carry enough data for the frontend to render a side-by-side review **without** relying on the `/preview` endpoint (which is being dropped in a separate PR — this PR just stops depending on it; it leaves `/preview` in place).

Today both the list and detail endpoints return the same flat `MergeCandidateView` (id, resource_ids, status, review/audit metadata). The detail response needs two additions so the client can render the review directly:

- **`resources`** — the full detail object for each resource in the candidate.
- **`compare`** — a per-field, cross-resource comparison block.

Scope is intentionally small and **API-only** (no frontend). The list endpoint is unchanged.

### Decisions already made (with the user)
- **Compute `resources`/`compare` live** from current state. PENDING and DENIED candidates render correctly. For APPROVED candidates the originals are repointed with memberships flipped INACTIVE, so their live-coalesced `data` is all-null; the merged data remains reachable via `merged_resource_id`. A "freeze snapshot on action" enhancement is **deferred to a later PR** (Jira ticket drafted below).
- **`resources` = full `OGFieldDetailView`** (data + provenance + raw `source_data`), plus the `compare` block. Keep `resource_ids` alongside `resources` (preserves original identity/order even when post-merge resources are null-shells).
- **List endpoint response is unchanged** (`MergeCandidateView`); only the detail endpoint gets a new, wider model.

## Success criterion

`GET /oil-gas-fields/merge-candidates/{id}` returns a model that includes the existing candidate fields **plus** `resources: list[OGFieldDetailView]` and `compare: list[FieldComparisonView]`, computed live, licensing-respecting, ordered by candidate item `position`. The list endpoint and all POST endpoints are byte-for-byte unchanged in shape. Tests cover PENDING (populated) and APPROVED (null-shell) cases.

## Approach

Reuse the existing coalescing/view machinery — do **not** re-implement source resolution.

### 1. New response models — `deployments/api/src/stitch/api/entities.py`
Add near `MergeCandidateView` (lines 161-172):

```python
class FieldValueView(BaseModel):
    resource_id: int
    value: Any

class FieldComparisonView(BaseModel):
    field: str
    status: Literal["match", "mismatch"]
    values: list[FieldValueView]

class MergeCandidateDetailView(MergeCandidateView):
    resources: list[OGFieldDetailView]
    compare: list[FieldComparisonView]
```

- Subclass `MergeCandidateView` so the shared candidate fields stay in sync.
- Import `OGFieldDetailView` from `stitch.ogsi.model`; `Any`/`Literal` from typing (file already imports `OilGasFieldBase`, `OGSISrcKey`).
- `compare` semantics (keep simple, per the chat): `status = "match"` iff every resource's value for that field is equal (Python `==`), else `"mismatch"`. This intentionally errs toward showing mismatches — exact float equality and ordered `owners`/`operators` list comparison will surface differences rather than hide them (matches the user's "err on the side of showing mismatches"). All-None fields compare equal → `"match"` (accurate; the client may choose to hide them). Document this in a short docstring on `FieldComparisonView`.

### 2. Action layer — `deployments/api/src/stitch/api/db/merge_candidate_actions.py`
Change `get_merge_candidate` to build and return `MergeCandidateDetailView` (this function is only consumed by the detail route; `list`/`create`/`approve`/`deny` use `_candidate_to_view` directly and are untouched):

- Signature gains `licensed_sources: Collection[OGSISrcKey] | None = None`.
- Load candidate via existing `_load_candidate_model`; derive ordered `resource_ids` from `items` (same pattern as lines 186-188).
- Build resources with the existing batch helper — `from .utils import coalesce_resources`, then `resource_to_detail_view` per id, preserving candidate order:
  ```python
  by_id = await coalesce_resources(session, resource_ids, licensed_sources)
  resources = [resource_to_detail_view(by_id[rid]) for rid in resource_ids]
  ```
  `coalesce_resources` (utils.py:65) already returns a null-shell view for repointed/no-data ids, which is exactly the live post-merge behavior we want.
- Add a private `_build_comparison(resources) -> list[FieldComparisonView]`: iterate `OilGasFieldBase.model_fields`, gather `getattr(r.data, field)` for each resource into `values`, set `status` per the rule above.
- Add a `_candidate_to_detail_view(model, resources, compare)` mirroring `_candidate_to_view` (reuse the same field mapping) plus the two new fields.
- Import `MergeCandidateDetailView`, `FieldComparisonView`, `FieldValueView` from `stitch.api.entities`; `resource_to_detail_view` + `coalesce_resources` from `.utils`.

### 3. Router — `deployments/api/src/stitch/api/routers/oil_gas_fields.py`
Update the `GET /merge-candidates/{id}` route (lines 106-120):
- `response_model=MergeCandidateDetailView`.
- Handler gains `claims: Claims` and passes `licensed_sources=licensed_sources(claims)` (same pattern as `get_resource_detail`, lines 279-285; `Claims` and `licensed_sources` are already imported).
- Import `MergeCandidateDetailView`.

### 4. Make the priority-override reset explicit (documentation only)
In `apply_resource_merge` (`deployments/api/src/stitch/api/db/og_field_resource_actions.py`, ~lines 201-249), where the new `ResourceModel` is created, add a comment noting: the merged resource is created fresh with **no** `og_field_resource_source_priority` rows, so it resolves fields in the **default** global source order; any per-field/per-resource priority overrides on the original resources are intentionally **not** carried over. No behavior change now (the fresh resource already has no overrides — confirmed in `og_field_resource_source_priority` keying); a later PR handles explicit reset if merge semantics ever preserve an existing resource.

## Files to change
- `deployments/api/src/stitch/api/entities.py` — new models.
- `deployments/api/src/stitch/api/db/merge_candidate_actions.py` — detail builder + comparison helper.
- `deployments/api/src/stitch/api/routers/oil_gas_fields.py` — route response_model + `claims` wiring + import.
- `deployments/api/src/stitch/api/db/og_field_resource_actions.py` — explanatory comment only.
- Tests (see below).

## Reused, not rebuilt
- `coalesce_resources` (`db/utils.py:65`) — batch coalesce; returns null-shell for repointed ids.
- `resource_to_detail_view` (`db/utils.py:142`) — builds `OGFieldDetailView`.
- `licensed_sources` (`api/permissions.py`) + `Claims` — licensing, same as `get_resource_detail`.
- `OilGasFieldBase.model_fields` — canonical field enumeration for `compare`.
- `_load_candidate_model` / `_candidate_to_view` field mapping.

## Tests — `deployments/api/tests/`
Follow existing patterns in `test_merge_candidate_actions.py` and `test_merge_candidate_preview.py`:
- PENDING candidate: detail returns `resources` (populated `data`/`provenance`/`source_data`) in item order, and `compare` with correct `match`/`mismatch` per field (include a field that differs and one that agrees).
- APPROVED candidate: after approve, detail returns null-shell `resources` (all-null `data`) — asserts/documents the deferred live behavior; `merged_resource_id` is set.
- Licensing: a non-licensed source is excluded from `resources`/`compare` (same claims mechanism as the detail-endpoint tests).
- `test_openapi.py`: update if it snapshots the schema for this route.

## Verification (end-to-end)
1. Run the API suite the repo's way (from `deployments/api/`, e.g. `uv run pytest tests/test_merge_candidate_actions.py tests/test_merge_candidate_preview.py tests/test_openapi.py`), then the full suite.
2. Drive the flow against a running API (create 2+ resources with differing source data → `POST /merge-candidates` → `GET /merge-candidates/{id}`): confirm `resources` carries per-resource detail and `compare` flags matching vs differing fields; then `POST .../{id}/approve` and re-`GET` to confirm null-shell resources + populated `merged_resource_id`.
3. Confirm the list endpoint (`GET /merge-candidates`) and OpenAPI for the POST endpoints are unchanged.

## Follow-up — Jira ticket to file (deferred freeze)
> **Title:** Freeze merge-candidate `resources`/`compare` snapshot on approve/deny
>
> **Body:** The merge-candidate detail endpoint (`GET /oil-gas-fields/merge-candidates/{id}`) computes `resources` and `compare` live. For APPROVED candidates the original resources are repointed with memberships flipped INACTIVE, so their live-coalesced data is all-null and the `compare` block is meaningless. Snapshot the computed `resources`+`compare` (or their inputs) at approve/deny time — likely a nullable JSON column on `merge_candidates` populated in `approve_merge_candidate`/`deny_merge_candidate` — and have the detail endpoint return the frozen snapshot for non-PENDING candidates, live for PENDING. Note: coordinate with the upcoming source-management rework, which may change the merge semantics and the frozen view schema.
