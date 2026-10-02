# Paginate the Merge Review candidate list (STIT-786)

## Context

`GET /api/v1/oil-gas-fields/merge-candidates` returns every candidate of every status as a bare array. The Merge Review page renders all of them, and each queue row fetches the full detail of every resource in its candidate just to show a name. After one link-all pass on production data (about 750 candidates), page load means one large list response plus about 1,500 detail requests, all rendered without virtualization.

**Jira:** **STIT-786 "Add paging to Merge Review page"** already exists (Backlog, reporter jhoffart, no description). We'll use it. Related tickets:
- **STIT-795** (sort control, Jason, Selected for Development). This plan covers its API and UI for *date* sorts. Alphabetical sort is deferred to a follow-up (see below). The user is coordinating with Jason.
- **STIT-745** (search, filter, sort, "virtualize or paginate"). This plan covers part of it: pagination and the status filter.

**Done when:**
1. The page fetches one page of candidates at a time, filtered to PENDING by default.
2. Queue rows render names with no per-row detail requests.
3. The header still shows whole-queue Pending, Reviewed and Total counts.
4. Status, page, page size and sort live in the URL.
5. Entity-linkage de-dupe still sees every candidate.
6. `make check` passes.

## Decisions (agreed)

- **Paging:** page-number paging using the existing `PaginationParams` / `PaginatedResponse` and the `Pagination` component.
- **Status filter:** a server-side, repeatable `status` param. No param returns all statuses. The frontend sends `status=PENDING` by default. The "Show approved" checkbox is replaced by a multi-select `FilterDropdown` (PENDING / APPROVED / DENIED), like the resource filters.
- **Counts:** add `status_counts` to the response. It's computed over the whole queue, ignoring the status filter, so the header numbers keep their current meaning.
- **Names:** the server computes `name` per candidate in this change. Name *sort* goes to a follow-up ticket.
- **Sort:** `sort_by ∈ {created, reviewed_at}` and `sort_order ∈ {asc, desc}`, default `created desc`, always with an `id` tiebreak. Today's order has no tiebreak, so bulk-created rows could shift between pages.

## API: `deployments/api`

1. **`entities.py`**
   - Add `MergeCandidateQueryParams(PaginationParams, …)` with `status: list[MergeCandidateStatus] | None`, `sort_by: Literal["created", "reviewed_at"] = "created"` and `sort_order = "desc"`, following the `OGFieldQueryParams` pattern (entities.py:101-131).
   - Add `name: str | None` to `MergeCandidateView`. `MergeCandidateDetailView` inherits it.
   - Add `MergeCandidatePage(PaginatedResponse[MergeCandidateView])` with `status_counts: dict[MergeCandidateStatus, int]`.
2. **`db/merge_candidate_actions.py`: `list_merge_candidates`** (line 203)
   - Accept params and `licensed_sources`. Apply the `status IN (…)` filter, then count, then `ORDER BY <sort>, id <same direction>` with `.limit/.offset`, following `og_field_resource_actions.py:57-90`.
   - `reviewed_at` is null for pending rows; put nulls last.
   - Run one `GROUP BY status` count query, unfiltered.
   - Fill in names in one batch: collect the page's resource ids and call `coalesce_resources(session, ids, licensed_sources)` (`db/utils.py:198`). Per candidate, pick the name whose provenance source ranks best in `SOURCE_PRIORITY`, with ties going to item position. This mirrors `pickCandidateName` (frontend `utils/mergeCandidateName.js:12`).
   - Have the detail view use the same helper so names agree.
   - Keep the `named_query` labels (`merge_candidates.list`, plus `.count` and `.status_counts`).
3. **`routers/oil_gas_fields.py:102`**
   - Set `response_model=MergeCandidatePage` and bind `Annotated[MergeCandidateQueryParams, Query()]`.
   - Pass `licensed_sources(claims)` through, the same way the resource list does.
4. **No migration in this change.** At about 750 rows, scanning on `status` and `created` is fine. If `merge_candidates.list` timings say otherwise, add an index on `(status, created, id)` later.
5. **`API_REFERENCE.md:89-97`:** update the response shape and params.

## Client and entity-linkage (same PR; the response shape changes)

- **`packages/stitch-client/.../async_client.py:430`**
  - Replace `list_merge_candidates` with `list_merge_candidates_page(page, page_size, status=None)`, which returns a dict.
  - Add `iter_merge_candidates(...)`, mirroring `iter_oil_gas_fields` (lines 170+) and `_validate_page_params`.
- **`deployments/entity-linkage/.../client.py:78` and `matching.py:182` `_existing_fingerprints`:** iterate every page with no status filter, at `MAX_PAGE_SIZE`, so de-dupe still covers reviewed candidates.

## Frontend: `deployments/stitch-frontend/src`

1. **`queries/api.js:192` `getMergeCandidates`:** accept `{page, pageSize, status[], sortBy, sortOrder}` and serialize `status` as repeated params, the way the resource filters do.
2. **`queries/resources.js:44-50, 122-132`**
   - Include the params in the list query key, keeping the `[endpoint, "merge-candidates", …]` prefix so review invalidation still works.
   - Add `placeholderData: keepPreviousData`, matching the resource list.
3. **`hooks/useResources.js:107` and mocks at 326:** pass the params through. Update the mock to return the paged shape.
4. **URL state:** add a merge-review-specific parse/serialize pair (page, page_size, status, sort_by, sort_order), styled after `config/listParams.js`.
   - It's a separate schema because `useListState` / `listParams` is tied to resource filters and columns. Generalizing it would be a refactor nobody asked for.
   - Default view is `status=PENDING`, page 1, page size 50, created desc, with defaults left out of the URL.
5. **`pages/MergeCandidateReviewPage.jsx`**
   - **Queue rendering**
     - Render `data.items`.
     - Replace the `showApproved` checkbox and the in-browser `visibleCandidates` filter (430-435) with a `FilterDropdown` for status.
     - Add a sort control (created / reviewed, asc / desc).
     - Put `<Pagination>` at the bottom of the sticky `QueuePanel`. It must fit the `md:max-h` flex column, so the list scrolls and the pager stays visible.
   - **Header and names**
     - Header counts come from `status_counts` (459-463, 517-536).
     - `CandidateQueueItem` uses `candidate.name` and drops `useMergeCandidateName` / per-row `useMergeSourceDetails`.
     - Check whether `useMergedResourceDetail` per row is still needed for merged rows. If so, keep it; it's only for approved rows, and those are filtered out by default.
   - **Selection**
     - Default selection stays "first PENDING on this page, else first item."
     - After a review, choose the next pending item from the current page's items.
     - If the page empties after refetch and `page > total_pages`, step back to the last page.
     - Clear the selection when the filter, sort or page changes and the selected id isn't in the new page.
   - **`hasHiddenApproved` (575-577):** replace with an empty-state message when the filter returns nothing, for example "No candidates match these statuses."
6. **Cleanup:** remove `useMergeCandidateName`, and `pickCandidateName` with its test, only if nothing else uses them after the change. The detail panel's source comparison still uses `useMergeSourceDetails`.

## Tests

- **API unit** (`tests/test_merge_candidate_actions.py`): status filter, the id tiebreak in ordering, `status_counts` ignoring the filter, name selection by source priority, and a null name when nothing is licensed.
- **API integration** (`tests/routers/test_merge_candidates_integration.py`, reusing `_create_candidate`):
  - paging across pages with identical `created` (no duplicates or gaps)
  - repeated `status` params
  - 422 on a bad `status`, `sort_by` or `page_size`, following `test_query_param_validation.py`
- **Update existing tests:** `test_route_permissions.py:139` (expects `[]`), `observability/test_query_name_actions.py:372`, `test_openapi.py`.
- **Client and linkage:** `stitch-client/tests/test_async_client.py` (iterator ends on `total_pages`), `entity-linkage/tests/test_matching.py` (fingerprints span multiple pages).
- **Frontend:**
  - `MergeCandidateReviewPage.test.jsx`:
    - adapt the fixtures to the paged shape
    - header counts come from `status_counts`
    - the status dropdown changes the query params
    - paging and URL round-trips
    - next-pending after review on a page boundary
    - names render with no `getResourceDetail` calls from the queue
  - Also update `queries/resources.test.js` (key prefix) and `queries/api.test.js` (param serialization).

## Suggested PR split (small, reviewable)

1. **API, client, entity-linkage, and a minimal frontend adaptation.** The frontend reads `.items` and sends `status=PENDING`, replacing the in-browser filter. The shape change breaks old callers, so these ship together.
2. **Frontend UI:** status dropdown, sort control, pager, URL state, server names in rows.

## Follow-up ticket to draft

- **"Sort Merge Review candidates by name"** (covers STIT-795's alphabetical requirement). It needs a SQL ranking of coalesced names across all candidates for each user's licensed sources.

## Verification

- `make check` from the repo root.
- `make dev-docker`, seed with `004-merge-demo.json`, and run entity-linkage `link_all` to create candidates. On `/merge-candidate-review`:
  - Only pending candidates show by default, and the header counts match the database.
  - The network panel shows one list request and no per-row `/detail` requests.
  - Paging, status and sort changes update the URL, and Back restores the previous view.
  - Approving the last pending item on a page moves the selection correctly.
- Re-run `link_all` and confirm it creates no duplicate candidates, so de-dupe still sees every page.
- For scale, set a small `page_size` (for example 2) to exercise paging with the demo data.
