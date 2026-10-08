# Bulk endpoints + one-pass Entity Linkage

## Context

A full Entity Linkage run takes about 15 hours on PROD data (STIT-757) and shows no progress while it runs (STIT-740, the umbrella ticket).

Today `link_all` streams `GET /oil-gas-fields/` 200 rows at a time. For each unprocessed resource it then makes about 1 + 1 + k requests: the seed detail, a `q=` search, and one detail per same-name hit. Each pair is then POSTed one at a time.

The Oct 2026 benchmark (`el-design-comparison-6e87bd/deployments/loadtest/el/results/REPORT.md`) found two things:
- Whole-table, one-pass matching over HTTP is orders of magnitude faster.
- A bulk, idempotent candidate write removes the 500/502 fingerprint races.

The prototype on `claude/hx-bulk-entity-linkage-abf6a1` (a6938c3c, 8c61198b, 92e9ec24, 2a3a2d0f) is a **reference to port from, not a base**. Its paths, params, permissions and N-way groups all differ from what's decided here.

Outcome: four PRs. Together they make `link_all` read the whole table in a few large keyset pages, match in memory in one pass, and write candidates in bulk.

A companion design document by Codex covers rationale and contract edge cases in more depth and serves as supporting design notes. Both plans agree on every decision below.

## Success criteria

1. **Bulk reads.** Authorized clients can scan coalesced resources and source records through the two new bulk GET endpoints, with projection, keyset paging and a large page size. The existing endpoints behave exactly as before.
2. **Licensing.** Bulk access never widens a caller's source licenses. Coalesced winners, filters, active-membership rules and resource visibility match today's list endpoints.
3. **Matching.** For a fixed dataset and set of permissions:
   - `link_all` makes one resource scan;
   - it produces the same name/country pair set as today, apart from documented Unicode differences;
   - a block of N resources produces N(N-1)/2 two-resource candidates, each exactly once.
4. **Bulk create.** Candidates can be created in a bounded batch with these properties:
   - each item gets its own result;
   - the database prevents duplicates;
   - review and audit fields behave as they do today.

## Decisions (confirmed)

**Permissions** are per-route and additive, so licensing never widens:
- `resource:read-bulk` together with `resource:read`, for `GET /oil-gas-fields/bulk`.
- `source:read-bulk` together with any `source:read:<key>`, for `GET /oil-gas-field-sources/bulk`.
  - Never `source:read:bulk`: that string sits in the source-key namespace.
- `merge-candidate:create-bulk` together with `merge-candidate:create`, for `POST /oil-gas-fields/merge-candidates/bulk`.

**Strict params**
- The bulk routes take only:
  - the existing filters (`OGFieldFilterParams`, `entities.py:103`);
  - `source` on the sources route only;
  - `fields`, `after_id`, `max_id` and `page_size`.
- Any other param, including `page`, `sort_by`, `sort_order`, or `source` on the fields route, gets a 422. This uses `model_config = ConfigDict(extra="forbid")`, which FastAPI ≥0.115 supports on query-param models.
  - Notes: the API runs FastAPI 0.141. The existing list endpoint accepts `source` on the fields route and ignores it.
- Order is always id ascending.

**Paging**
- `after_id` is exclusive. `max_id` is an inclusive upper bound, so a page covers `after_id < id <= max_id`.
- **When `max_id` is omitted**, the server reads the **table's** current highest id: `max(og_field_resources.id)` or `max(oil_gas_field_sources.id)`, and 0 if the table is empty.
  - This is one primary-key lookup. It is not filtered and it is not a count.
- The response always returns the effective bound: `{items, next_after_id, max_id}`.
  - Clients carry that `max_id` forward, so the scan is bounded and excludes rows inserted later.
  - `max_id` is only a number limiting the scan. Rows at or below it still follow every filter, licensing and visibility rule.
- **The bound is not a snapshot.** Pages run as separate read-committed requests, so:
  - existing rows' values and memberships can change between pages;
  - rows can move into or out of the filtered set;
  - a lower id allocated earlier can commit late and be missed.

  A strict snapshot across requests would need its own design and is out of scope. The docs should describe this as a "bounded live scan".
- **`next_after_id` is the id of the last row returned**, not the look-ahead row's id. If a page returns ids 1–100 and looks ahead at 101, it returns `next_after_id=100`. It is `null` when there is no look-ahead row.
- `page_size` defaults to 10000 with a maximum of 10000. Tune later.
- There is no total count.

**Projection**
- `fields` is a repeated param (`?fields=name&fields=country`) taking flat attribute names.
- Identity fields are **always** included: `id` on fields rows, and `id` + `source` on source rows.
  - Passing an identity name in `fields` is accepted and does nothing. Identity names are **removed from the projected attribute list before rows are built**, so `fields=id` returns identity-only rows and can never overwrite `id` (or `source`) with `null`.
  - Repeated names are de-duplicated.
- Omitting `fields` returns every attribute. An unknown name or an empty value (`?fields=`) gets a 422.
- Fields rows hold coalesced winning values only, with no provenance. A winner is chosen per attribute under the existing priority rules.
- Values keep their types: `owners` and `operators` stay arrays of objects.
- **`null` means no licensed source supplies a value** for that attribute, either because no source has it or because only unlicensed sources do. Unrequested attributes are absent from the row, not `null`.
- Source rows carry that source record's own values, with no coalescing. `source_record` is never included.

**EL behaviour**
- Matching uses coalesced name+country only.
- Blocks of 3 or more become all C(N,2) pairs (`pairwise_candidates`, `matching.py:55`).
- **Individual linking (`link_resource`) is unchanged.**
- Unicode parity between `link_all` and `link_resource` is not required, but the gap is documented. One-pass casefold may pair ß/ss-style names that `link_resource`'s ILIKE pre-search misses.
- **The current failure counting is kept.** When a pair's write fails, the rest of that block is not attempted, `resources_failed += 1` for the block, and the run continues (`matching.py:225-265`).
- **Blocks are built while pages are read.** Only a `key → ids` dict is held, never the whole row table.
- **`BulkLinkResponse` is unchanged.** The docs note that an `errors` list should be considered later.

**Bulk create**
- The request mirrors the single create: `{"items": [{"resource_ids": [...]}, ...]}`.
  - At most 10000 items and **100,000 total ids** per request (counting repeats); over that is a 422.
- The response has one result per item, in input order: `{status: "created"|"existing"|"rejected", candidate_id, reason, status_code}`.
  - `reason` is a short plain string, with no error-code taxonomy.
  - `status_code` is set only on rejected items. It is 400 for invalid or already-merged resources and 404 for missing ones, matching the single create.
  - It lets PR4 keep today's rule (400 = skip, 404 = failed block) without parsing text.
- `existing` is reported **before** merged-resource checks.

**Tests** assert there are no `COUNT`, no `OFFSET` and no per-row (N+1) queries on the bulk paths.

## PR structure

| PR | Base | Jira |
|----|------|------|
| 1: bulk reads | main | STIT-757 |
| 2: one-pass `link_all` | PR1 (retarget to main after PR1 merges) | STIT-757 |
| 3: bulk merge-candidate create | main | STIT-757 |
| 4: EL bulk submit | main, after PR2 and PR3 merge | STIT-757 (refs STIT-719) |

- PR1 and PR3 both add constants to `packages/stitch-auth/.../permissions.py` and both edit `routers/oil_gas_fields.py` and `entities.py`. Whichever merges second gets small conflicts.
- **External prerequisite:** the new permissions must be created in the Auth0 tenant (`rmi-spd`) and granted to the EL service token:
  - before PR2 deploys: `resource:read-bulk`;
  - before PR4 deploys: `merge-candidate:create-bulk`.

  Local dev works without this, because `AUTH_DISABLED` grants `ALL_PERMISSIONS`.

---

## PR 1 — Bulk read endpoints (off main)

### Commit 1: `feat(api): add keyset-paged bulk read endpoints (STIT-757)`

**Auth** (`packages/stitch-auth/src/stitch/auth/permissions.py`, `__init__.py`)
- Add `RESOURCE_READ_BULK` and `SOURCE_READ_BULK` to `ALL_PERMISSIONS`.
- Do **not** add them to `SOURCE_READ_PERMISSIONS`.
- Add a test that `source:read-bulk` never parses as a licensed source (`source_read_sources`).
- Check `stitch-frontend/src/App.test.jsx:60-73`, which hard-codes a permission list.

**Params and response** (`deployments/api/src/stitch/api/entities.py`)
- `OGFieldBulkQueryParams(OGFieldFilterParams)`:
  - `extra="forbid"`;
  - `fields: list[BulkFieldName] | None`, a Literal of the identity names plus `OilGasFieldBase.model_fields`. This avoids the `db.model` circular import, as in the prototype.
  - `after_id: int = Field(0, ge=0)`;
  - `max_id: int | None` (ge=0);
  - `page_size: int = Field(10000, ge=1, le=10000)`.
- `OGFieldSourceBulkQueryParams(OGFieldBulkQueryParams)` adds `source` with the list default.
- `BulkPage{items: list[dict[str, Any]], next_after_id: int | None, max_id: int}`.
- Constants: `BULK_DEFAULT_PAGE_SIZE` and `BULK_MAX_PAGE_SIZE`.

**Queries** (`db/queries.py`)
- Port the prototype's optional `colnames` on `construct_base_query_statement` and `coalesced_winner_rows`, so that only the requested attributes are ranked.
- Bulk actions build an `OGFieldQueryParams` from the filter dump with `sort_by="id", sort_order="asc"`. They then reuse `base_resource_query` / `base_source_query` unchanged, which keeps the same universe, filters and licensing.

**Actions**

`og_field_resource_actions.bulk(session, params, licensed_sources)`:
1. If `max_id` is None, run `SELECT max(id) FROM og_field_resources`; an empty table gives 0.
2. Build the ids statement.
3. Apply `id > after_id`, `id <= max_id` and `limit(page_size + 1)`.
4. If more than `page_size` ids come back, drop the look-ahead id and set `next_after_id` to the **last kept id**. Otherwise `next_after_id` is None.
5. Compute `attrs`: the requested `fields` minus the identity names, de-duplicated, or every attribute when `fields` is omitted.
6. Hydrate the kept ids with one `coalesced_winner_rows(ids, licensed, colnames=attrs)` call and `materialize_value`. If `attrs` is empty (identity only), skip hydration.
7. Build each row as `{**dict.fromkeys(attrs), "id": rid}`, filling in the winners. Null shells survive, and identity is written last so it can never be nulled.
8. Return `BulkPage(items, next_after_id, max_id)`.

`og_field_source_actions.bulk(...)` follows the same steps 1, 3, 4, 5 and 8. In step 5 it removes both `id` and `source` from `attrs`.
1. Its bound is `max(oil_gas_field_sources.id)`, and its keyset is on `source_pk`, using `base_source_query`.
2. Load one headers query (`id, source`; never `source_record`).
3. Load one values query: `source_pk IN page AND colname IN attrs`. Skip it when `attrs` is empty.
4. Pivot in Python, because Postgres has no `max(json)`. Write `id` and `source` from the header last.

Both actions return an empty terminal page when `after_id >= max_id`.

Wrap the queries in `named_query(...)` and add the cases to `tests/observability/test_query_name_actions.py`.

**Routes**
- `routers/oil_gas_fields.py`: `GET /bulk`, declared above `/{id}`.
- `routers/oil_gas_field_sources.py`: `GET /bulk`, declared above `/{id}`, with both permission dependencies.
- The existing list routes don't change.

**Tests** go in a new `deployments/api/tests/routers/test_bulk_routes.py` on `integration_client`, ported from the prototype's `test_export_routes.py` and extended. They cover:

Params and projection:
- projection with identity always present, and omitted `fields`;
- `fields=id`, and `fields=id&fields=source` on the sources route: identity-only rows with real ids and sources, never `null`;
- `fields=name&fields=name`: de-duplicated;
- a resource whose only `name` comes from an unlicensed source returns `name: null`;
- `owners` keeps its array-of-objects shape;
- 422s for:
  - an unknown field;
  - an empty `fields=` value;
  - `page`, `sort_by` or `sort_order`;
  - `source` on the fields route;
  - `page_size` of 0 or 10001.

Paging:
- keyset coverage over non-contiguous ids;
- **`next_after_id` equals the last returned id.** With ids 1..5 and `page_size=2`, the pages are [1,2], [3,4], [5] and nothing is skipped.
- a final page that is an exact multiple of `page_size`;
- `after_id` past the end;
- `max_id`:
  - when omitted, it is set to the table's highest id, returned, and stays the same on every page;
  - **the bound is unfiltered.** When the table's highest row is excluded from the results, `max_id` still equals that row's id. Cover each case separately: filtered out, unlicensed, inactive membership, and repointed.
  - a resource inserted after the first page with a higher id is excluded when the old `max_id` is passed;
  - a caller-supplied `max_id` is respected;
  - an empty table gives `max_id=0` and one empty terminal page;
  - **a non-empty table whose filtered result is empty** gives the table's `max_id` and one empty terminal page.

Data rules:
- the filters, including repeated `country` and `q`, and `source` on the sources route;
- repointed and inactive rows excluded;
- licensing through restricted clients, in the style of `test_licensed_sources_routes.py`.

**No count/offset/N+1:**
- Capture SQL with `event.listen(engine.sync_engine, "before_cursor_execute")`.
- Assert that no statement contains `count(` or `OFFSET`.
- Assert that the statement count is the same for a 2-row page and a 20-row page.

Also add `test_route_permissions.py` rows (two routes × each missing permission) and the new paths in `tests/test_openapi.py`.

**Docs**: regenerate `deployments/api/API_REFERENCE.md` with `scripts/api_doc.py gen`.

### Commit 2: `feat(client): add bulk read methods (STIT-757)`

Changes go in `packages/stitch-client/src/stitch/client/async_client.py` and `__init__.py`.
- Add `MAX_BULK_PAGE_SIZE = 10000`.
- Add `list_oil_gas_fields_bulk_page(*, fields=None, after_id=0, max_id=None, page_size=10000, <filters>)` and `iter_oil_gas_fields_bulk(...)`.
  - The iterator takes `max_id` from the first response, or from the caller, and sends it on every later page.
  - It follows `next_after_id` until that is null.
  - It raises if the server's returned `max_id` changes mid-scan.
  - The filters are explicit, typed kwargs covering `OGFieldFilterParams`, like the existing `q`/`name`/`country`.
- Add `list_oil_gas_field_sources_bulk_page` and `iter_oil_gas_field_sources_bulk`, which add `source`.
- `fields` is a `Sequence[str]` sent as repeated params. A bare `str` raises `TypeError`. A `page_size` outside 1..10000 raises `ValueError`.
- The iterator raises if:
  - `next_after_id` doesn't advance;
  - any row lacks its identity fields (`id` on fields rows; `id` and `source` on source rows).

  It never infers the end from a short page.
- The new methods reuse `_request_json` and the GET retry path. The old methods and `MAX_PAGE_SIZE=200` are untouched.
- Tests in `packages/stitch-client/tests/test_async_client.py` use `httpx.MockTransport`. They cover repeated-param encoding, validation, cursor following, a stalled cursor, a row missing an identity field, `max_id` pinned from the first page, and a changed `max_id` raising.

---

## PR 2 — One-pass `link_all` (on PR1)

### Commit: `feat(entity-linkage): link all resources in one pass (STIT-757)`

Files are under `deployments/entity-linkage/src/stitch/entity_linkage/`.

**`client.py`**: add `iter_match_rows(page_size)`, which wraps `iter_oil_gas_fields_bulk(fields=("name", "country"), page_size=...)` and yields `FieldCandidate`.

**`matching.py`**

New `async def find_match_blocks(rows: AsyncIterable[FieldCandidate]) -> tuple[list[list[int]], int]`, which builds blocks **as the pages stream in**:
- For each row, compute the key `(normalize_name(name), normalize_country(country))` and append the id to `ids_by_key[key]`. This is the same rule as `find_match_group_for_resource`. Rows with an empty or missing name or country are counted but not keyed.
- Each page's rows are dropped once folded in. Peak memory is the key → ids dict plus one page, never the full row table.
- At the end it keeps only keys with 2 or more ids, as sorted lists, and sorts the blocks for a deterministic order. It returns `(blocks, rows_scanned)`.
- Exact-key equality is already transitive, so no union-find is needed.
- It stays pure (no I/O of its own), so tests can drive it with a plain async generator.

`link_all` is rewritten:
1. Call `blocks, resources_scanned = await find_match_blocks(client.iter_match_rows(page_size))`.
   - The whole scan finishes before any write.
   - `resources_scanned` counts every row, including null shells.
2. Then, if `apply_merges`, run `_existing_fingerprints`.
3. For each block, keep the **existing inner loop as-is**:
   - `pairwise_candidates`;
   - the run-local fingerprint de-dupe;
   - `_submit_group`, where a 400 counts as skipped;
   - the existing `try/except (StitchAPIError, httpx.HTTPError, OSError)` **around the block**. A failing pair stops that block, adds 1 to `resources_failed`, and the run continues.

On scan failures:
- A failure during the scan (after the client's GET retries) fails the job, and nothing is written from a partial table.
- This replaces today's per-resource read-error skip, because per-resource reads no longer exist. Call this out in the PR.

Code cleanup:
- Remove only the code orphaned by the rewrite (the `link_all` streaming/processed-ids loop).
- `find_match_group_for_resource`, `link_resource` and the router's single route are unchanged.

**`routers/link.py`**: `BulkLinkRequest.page_size` becomes the bulk page size.
- The cap and the default both go to 10000 (`MAX_BULK_PAGE_SIZE`); tune later. The 50K benchmark measured 5000-row pages at about 100 ms.
- 200 stays valid. The frontend doesn't send this field.
- No silent fallback to the old listing if the bulk permission is missing; the 403 surfaces as a failed job.

**Tests**

`tests/test_matching.py`:
- Add a bulk iterator to `FakeMatchingClient`.
- `find_match_blocks`:
  - a 3-block gives 3 pairs and a 4-block gives 6;
  - a block whose members span several pages comes out whole;
  - casefold and whitespace handling;
  - blank keys are skipped but still counted;
  - the output is deterministic.
- For a resource, its `find_match_group_for_resource` result equals its block from `find_match_blocks`, for ASCII data.
- `link_all`:
  - exactly one scan, with no detail or search calls;
  - no writes on a dry run or a failed scan;
  - failure counting: the rest of the block is skipped and the next block still runs.

Also update the fakes in `tests/test_link_api.py`.

**Docs**: update the `deployments/entity-linkage/README.md` linkage flow (lines 9–30) with two additions:
- a short note on the Unicode difference from `link_resource`;
- a "future consideration" note that `BulkLinkResponse` could gain an `errors` list. Today, failures are only logged.

---

## PR 3 — Bulk merge-candidate creation (off main)

### Commit 1: `feat(api): add bulk merge-candidate creation (STIT-757)`

**Auth**: add `MERGE_CANDIDATE_CREATE_BULK = "merge-candidate:create-bulk"` to `ALL_PERMISSIONS`.

**Models** (`entities.py`)
- `MergeCandidateBulkCreateRequest{items: list[MergeCandidateBulkItem] = Field(max_length=10000)}`, where `MergeCandidateBulkItem{resource_ids: list[int]}`.
  - A model validator caps the total ids across items at 100,000 (`MAX_BULK_CREATE_IDS`); over that is a 422.
  - Each inner list is deliberately unconstrained, so one bad item is rejected on its own and doesn't fail the batch with a 422.
- `MergeCandidateBulkResult{status: Literal["created", "existing", "rejected"], candidate_id: int | None, reason: str | None, status_code: int | None}`.
  - `status_code` is 400 or 404 and is set only when the item is rejected.
- `MergeCandidateBulkCreateResponse{results: list[MergeCandidateBulkResult]}`, in input order.

**Action** (`db/merge_candidate_actions.py::create_merge_candidates_bulk`, ported from the prototype with the checks reordered)
1. For each item:
   - de-dupe while keeping order;
   - reject with 400 if it has fewer than 2 distinct ids (`"fewer than 2 distinct resource ids"`) or its fingerprint is too long;
   - compute `_fingerprint`.
2. Look up existing fingerprints in chunks, in any status. Mark those items `existing` with their candidate id. **This happens before the resource checks.**
3. Look up the remaining ids in chunks (`id, repointed_id`):
   - reject with 404 `"resources not found: [...]"`;
   - reject with 400 `"resources already merged: [...]"`.

   These codes match the single create's mapping.
4. Insert the rest with a dialect-local `insert().on_conflict_do_nothing(index_elements=["fingerprint"]).returning(id, fingerprint)` in chunks. Use the user's audit columns.
   - Fingerprints that conflict, meaning a concurrent insert won, are re-read and reported as `existing`.
   - A repeat inside the batch is reported as `existing` with the first occurrence's id.
5. Insert `MergeCandidateItemModel` rows (with `position`) only for created candidates, using a chunked executemany.

The whole operation runs in the request's UoW, and an unexpected error rolls everything back and returns 500. Add `named_query` labels and observability-test cases.

**Scope**: this only creates PENDING candidates. It never approves, merges or revives a DENIED candidate, and it never changes an existing candidate's review or audit fields.

**Caveats to document** in the docstring and API reference:
- **Retries.** The fingerprint constraint stops duplicates, but it is not a log of past requests.
  - If a response is lost and the request is retried, the retried items come back `existing` instead of `created`, and may reflect reviews that happened in between.
  - The client keeps its conservative POST retry policy, and no idempotency-key mechanism is added.
- **Concurrent review.** The fingerprint constraint doesn't serialize a bulk create against a curator approving or merging the same resources at the same moment.
  - The single create already has this gap, and this PR doesn't make it worse.
  - If stronger coordination is ever needed, that is a separate design decision about the review actions.

**Route**: `POST /oil-gas-fields/merge-candidates/bulk`.
- It requires `MERGE_CANDIDATE_CREATE` and `MERGE_CANDIDATE_CREATE_BULK`, and returns 200.
- It is declared before any `/{id}` routes, like the other static paths.

**Tests** (`tests/routers/test_merge_candidates_bulk.py`, integration):
- created pairs and an N-way item;
- a repeat call returning `existing` with the same ids;
- an existing DENIED candidate returning `existing`;
- **an existing candidate whose resources have since merged returning `existing`**;
- a duplicate inside the batch;
- each rejection reason;
- an empty batch;
- 422 at 10001 items, and at 100,001 total ids;
- `status_code` on each rejection kind;
- order kept;
- items written only for created candidates, with audit columns and `position`;
- the same statement count for 2 items and 50 items (no N+1);
- `test_route_permissions.py` rows.

Regenerate `API_REFERENCE.md`.

### Commit 2: `feat(client): add bulk merge-candidate creation (STIT-757)`

- `create_merge_candidates_bulk(resource_id_groups: Sequence[Sequence[int]]) -> list[dict]` sends `{"items": [{"resource_ids": ...}]}` and returns `results`.
  - It raises `ValueError` above `MAX_BULK_CREATE_ITEMS = 10000` items or `MAX_BULK_CREATE_IDS = 100000` total ids.
- The existing conservative POST retry policy is kept.
- `MockTransport` tests cover the payload shape, order, validation and error mapping.

---

## PR 4 — EL writes through bulk create (off main after PR2 and PR3)

### Commit: `feat(entity-linkage): submit merge candidates in bulk (STIT-757)`

`matching.link_all` (apply only; a dry run is unchanged):
- Generate pairs block by block, in deterministic order. Keep the run-local fingerprint de-dupe.
- Fill batches of up to `_BULK_CREATE_BATCH` items (start at 10000, tune later). Track each pair's block index.
- Send the batches **one after another**. A block that has already failed has its remaining pairs dropped before the next batch is built.
- Map each item result:
  - `created`: `created += 1`, and the pair goes into `match_groups`;
  - `existing`: `skipped += 1`, and the pair goes into `match_groups`;
  - `rejected` with `status_code == 400`: `skipped += 1`, and **the pair stays in `match_groups`**, the same as today's 400-as-skip. The reason is logged.
  - `rejected` with any other code (404): the block is marked failed and the pair is not added to `match_groups`, as today, where a raised error never appends the pair.
- **Failure counting is kept at block level.** A `failed_blocks` set means each failed block adds exactly 1 to `resources_failed`, however many of its pairs fail.
- A failed batch request (`StitchAPIError`, `httpx.HTTPError` or `OSError`) marks every block with a pair in that batch as failed (each counted once). Results from earlier batches stay counted, and the run continues with the next batch.
  - Nothing guesses whether the failed batch committed. The existing conservative POST retry policy is kept.
- Programming errors still fail the job.
- Drop the `_existing_fingerprints` preload, which is an unpaginated list of every candidate. The server now reports `existing`.
- `BulkLinkResponse` is unchanged.
- `link_resource` is unchanged: it still uses the single POST.

**Documented timing difference:** a batch is sent as a whole. If one pair in a block fails, other pairs from that block **in the same batch** can still succeed, whereas the old one-at-a-time loop would have stopped before them. Their real results are kept and counted, and only later batches skip the failed block. This goes in the README and the PR description.

**Tests**:
- several batches, including a block that spans a batch boundary;
- results mapped to counters in input order;
- a 400 rejection is skipped and kept in `match_groups`, while a 404 rejection fails the block and is left out;
- several failures in one block count once;
- a failed batch counts its blocks once, earlier results are kept, and the run continues;
- a failed block's pairs in later batches are not sent;
- a dry run makes no POSTs;
- there is no candidate-list preload.

Update the README, including the `errors`-list future-consideration note.

---

## Rollout

1. **API first.** Deploy PR1 and PR3. Both are additive, and the existing endpoints are unchanged.
2. **Grants.** In Auth0:
   - create `resource:read-bulk`, `source:read-bulk` and `merge-candidate:create-bulk`;
   - grant `resource:read-bulk` and `merge-candidate:create-bulk` to the EL service identity;
   - check that the identity still holds its existing `source:read:*` licenses and `merge-candidate:create`.
3. **EL reads (PR2).** Deploy, then smoke-test a dry run in a non-production environment.
4. **EL writes (PR4).** Deploy, then smoke-test an apply on a small dataset in a non-production environment.

The inbound `service:entity-linkage:run` permission is unchanged.

EL can be rolled back on its own while the additive API endpoints stay in place. Candidates that a run has already created persist after any rollback.

---

## Verification

For each PR:
- Run `make check`.
- Run the focused targets:
  - `make api-test`;
  - `make pkg-test-auth`;
  - `make pkg-test-client`;
  - `make entity-linkage-test`.

Functional checks against a local stack (`make api-dev` / `make dev-docker`, seeded):
- **PR1**:
  - Page `GET /api/v1/oil-gas-fields/bulk?fields=name&fields=country` by `after_id`, carrying the `max_id` from the first page.
  - Confirm every id appears exactly once and that the count matches the list's `total_count` under the same filters.
  - Confirm a 403 without `resource:read-bulk` and a 422 for `sort_by`.
- **PR2**:
  - Run a dry run on main and on PR2 against the same data.
  - The `match_groups` pair sets should be equal, except for any casefold-only (Unicode) pairs. List those in the PR.
- **PR3**:
  - POST a batch twice. The second call should return every item as `existing`.
- **PR4**:
  - Run an apply on PR2 and on PR4 from the same starting state.
  - The created, skipped and failed totals and the `match_groups` should match, apart from the documented batch timing difference.
