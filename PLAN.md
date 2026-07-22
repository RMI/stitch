# Create source & attach to existing resource (STIT-527 / STIT-538)

## Context

Today, creating a source always creates a resource too. The LLM "Add to resource"
flow is the clearest example: the frontend builds a brand-new resource whose only
`source_data` entry is the LLM source, `POST`s it (`createResource`), then creates a
merge candidate linking that throwaway resource to the target
(`createMergeCandidate`) for later human merge review.

We want to **create a source and attach it directly to an existing resource** in one
step — no throwaway resource, no merge candidate. This matches:

- **STIT-527** ("Improve Source creation flow"): creating a source should resolve an
  *existing* resource, preserving the invariant that **a source is always attached to
  at least one resource**.
- **STIT-538** ("Add endpoint to attach sources to a resource"): proposes a
  resource-scoped `POST v1/oil-gas-fields/:id/...` endpoint whose body is source
  model(s).

This is **PR 1 of 2**. The next PR (**STIT-495**, "RMI_CUSTOM field overwrite from
Resource Detail") lets a user type a curated field value stored as an `RMI_CUSTOM`
source that wins coalescing — i.e. the *same* create-and-attach endpoint with
`source: "rmi"` and a user-entered value. So this PR is STIT-495's foundation; it is
**out of scope here** beyond leaving clean seams.

### Decisions (confirmed)

- **Endpoint:** single resource-scoped `POST /oil-gas-fields/{id}/sources`.
- **Body:** one `OGFieldSource` (no `id`); **response:** created `OGFieldSourceView`.
- **Permissions:** statically require **both** `source:write` + `resource:write`
  (attachment always happens, so no conditional check is needed).
- **Bare-create route** `POST /oil-gas-field-sources/`: **keep but deprecate**
  (unused in production — only tests + `API_REFERENCE.md` reference it). Remove fully
  in a later PR once STIT-527's data-model work lands.
- **Frontend gating:** adopt a `usePermissions` hook to gate the button.
- **Deliverable:** implement the change and leave it in the working tree (no commit,
  no push). I will **not** open the PR — I'll surface a proposed PR description in the
  thread for you to use.

## Success criteria

1. `POST /oil-gas-fields/{id}/sources` with a source body creates the source, creates
   an ACTIVE membership to resource `{id}`, and returns the created source (with its
   new id) — atomically (rolls back if the resource doesn't exist).
2. Requires both `source:write` and `resource:write`; missing either → 403.
3. The attached source appears in `GET /oil-gas-fields/{id}/detail` and participates
   in coalescing (its value can win per priority).
4. The LLM "Add to resource" button uses the new endpoint: no new resource, no merge
   candidate. Button is hidden/disabled when the user lacks the permissions.
5. Bare-create endpoint still works but is marked deprecated.

## Approach

### Backend (`deployments/api`)

**1. New action** in `src/stitch/api/db/og_field_source_actions.py` — reuse existing
helpers, no duplicated membership logic:

```python
async def create_and_attach_source(session, user, source, resource_id) -> OGFieldSource:
    if source.id is not None:
        raise SourceIntegrityError("Cannot create a source with a client-supplied id")
    created = await create_source(session, user, source)               # existing
    await attach_sources_to_resource(session, resource_id, [created], user)  # existing
    return created
```

- `create_source` (line 28) validates + persists the new source (assigns id).
- `attach_sources_to_resource` (line 96) already does the resource-existence check
  (`ResourceNotFoundError`) and membership creation; passing the id-bearing `created`
  routes it through `_get_or_create_source_models`' "existing" branch (fetch, then
  membership). Both run in the request's single UnitOfWork → atomic.
- Note: `OilGasFieldSourceModel._build` silently ignores a supplied id today, hence
  the explicit `SourceIntegrityError` guard for clarity.

**2. New route** in `src/stitch/api/routers/oil_gas_fields.py` (prefix `/oil-gas-fields`):

```python
@router.post(
    "/{id}/sources",
    response_model=OGFieldSourceView,
    dependencies=[Depends(require_permissions(RESOURCE_WRITE, SOURCE_WRITE))],  # check="all"
)
async def create_and_attach_source(*, uow, user, id: int, source: OGFieldSource):
    try:
        return await og_field_source_actions.create_and_attach_source(
            session=uow.session, user=user, source=source, resource_id=id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SourceIntegrityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- Add imports: `SOURCE_WRITE` (from `stitch.auth.permissions`), `OGFieldSource` &
  `OGFieldSourceView` (from `stitch.ogsi.model`), `og_field_source_actions`,
  `SourceIntegrityError`.
- Path `/{id}/sources` does not collide with the existing
  `GET /{id}/fields/{field}/sources` (field source values).

**3. Deprecate bare-create** in `src/stitch/api/routers/oil_gas_field_sources.py`: add
`deprecated=True` to the `POST "/"` decorator and a docstring line pointing to
`POST /oil-gas-fields/{id}/sources`. Leave behavior unchanged.

**4. Docs:** in `deployments/api/API_REFERENCE.md`, add the new endpoint and note the
bare-create `POST /oil-gas-field-sources/` as deprecated.

### Frontend (`deployments/stitch-frontend`)

**5. API client** — add to `src/queries/api.js`:

```js
export async function createSourceForResource(
  config, resourceId, sourcePayload, fetcher, endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${resourceId}/sources`;
  // POST JSON sourcePayload; same ok/getErrorDetail handling as createResource
}
```

**6. Permissions hook** — add `src/hooks/usePermissions.js`, mirroring PR #174's
implementation exactly (fetch `GET /auth/me`, read `payload.claims.permissions`,
cached; export `usePermissions()` and `useHasPermission(permission)`). `GET /auth/me`
already exists on main (`routers/auth.py`, returns `claims.permissions`). *Keep this
file byte-identical to #174's so the second-merged PR resolves trivially.*

**7. Rework `AISuggestionPanel`** in `src/pages/ResourceDetailPage.jsx`:

- Replace `buildLLMResourcePayload` (resource wrapper) with `buildLLMSourcePayload`
  returning just the source object (the current `source_data[0]` shape: `source:"llm"`,
  the suggested field, and the `source_record` audit payload).
- `handlePersistSuggestion`: single call
  `createSourceForResource(config, resourceId, sourcePayload, fetcher, endpoint)`; on
  success invalidate `resourceKeys.detail(endpoint, resourceId)` and the field's
  `resourceKeys.fieldSources(...)` so the new source shows immediately. Drop the
  two-call `partial` state; update copy to e.g. "Source added to resource."
- Gate the button:
  `const canAttach = useHasPermission("source:write") && useHasPermission("resource:write")`
  — hide/disable when false.
- Remove `buildLLMResourcePayload` (replaced by `buildLLMSourcePayload`). Keep
  `buildSuggestionAuditPayload`, `LLM_AUDIT_PRODUCER`, `createPersistIntentId`, and
  `getSuggestionSubmissionKey` — all still used (audit payload → `source_record.payload`,
  intent id → `source_record.record_id`, suggestion key → button dedupe).

**8. Remove orphaned code** (per decision — this change is their only app-code caller):

- Delete `createResource` and `createMergeCandidate` from `src/queries/api.js`, and
  their two `describe` blocks + imports in `src/queries/api.test.js`.
- Remove their imports/usage from `ResourceDetailPage.jsx` (done in step 7).
- Verified there are **no other orphans**: no create-mutation hooks in
  `useResources.js`, no re-exports; the merge-candidate *review* path
  (`getMergeCandidate(s)`, `reviewMergeCandidate`, review page) is untouched and stays.

### Tests

- **Backend route permissions** — add cases to
  `tests/routers/test_route_permissions.py`'s parametrized table: POST
  `/oil-gas-fields/{id}/sources` returns 403 when missing `source:write` and when
  missing `resource:write` (two rows).
- **Backend functional** — new test (fits `tests/db/test_resource_actions.py` or a new
  routes test alongside `test_licensed_sources_routes.py`): create+attach → membership
  exists, source appears in resource detail and can win coalescing; 404 on missing
  resource; 400 when body carries a source `id`.
- **OpenAPI** — `tests/test_openapi.py` currently asserts the bare-create path exists;
  keep that (still present, deprecated) and optionally assert the new path.
- **Frontend** — `src/queries/api.test.js`: add `createSourceForResource`, delete the
  `createResource`/`createMergeCandidate` blocks. Rewrite the persist tests in
  `ResourceDetailPage.test.jsx` (lines ~474–696 currently spy on the old two-call flow)
  to the single `createSourceForResource` call + button-gating behavior. Add a
  `usePermissions` test mirroring #174 if practical.

### Seams for later (do NOT implement here)

- **STIT-495:** reuses `POST /oil-gas-fields/{id}/sources` with `source:"rmi"` and a
  user value; its edit action lives on the field card near PR #174's reprioritize
  edit button.
- **STIT-527:** membership is created **ACTIVE** (direct attach, no review). The
  future PENDING state (suggest/approve split) belongs at this endpoint — it can set
  status by permission (e.g. a future create-vs-approve split). Attaching *existing*
  sources by id (STIT-538 optional) is a cheap extension: `attach_sources_to_resource`
  already accepts id-bearing sources.

### Coordination

PRs #170 (coalesce → DB) and #174 (reprioritize + `usePermissions`) touch overlapping
files (`oil_gas_fields.py`, `og_field_resource_actions.py`, `api.js`, `useResources.js`)
and both drop merge-preview. Expect light merge coordination; keep `usePermissions.js`
identical to #174's.

## Verification

- **Backend:** `make api-test` (or `cd deployments/api && uv run pytest`). Manual with
  `AUTH_DISABLED=true`: `POST /api/v1/oil-gas-fields/{id}/sources` with an `llm` (or
  `rmi`) source body → 200 + created source; `GET /api/v1/oil-gas-fields/{id}/detail`
  shows the source and coalesced value; bad `{id}` → 404; body with a source `id` →
  400. With auth on, confirm 403 when a required permission is absent.
- **Frontend:** `make frontend-test` (vitest). Manual (`run` skill / dev server): open
  a resource detail, generate an AI suggestion, click "Add to resource" → source
  attaches to the *current* resource (no new resource, no merge candidate) and appears
  in its sources; the button is hidden/disabled without the permissions.
