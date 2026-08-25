# STIT-418 — Redirect repointed resources to their merged target

## Branch / main status (checked 2026-08-27)

`origin/main` and local `main` are both at `3660b5f`. `feat-redirect` is **0 behind /
1 ahead** of `origin/main` (the single "Add PLAN" commit). The branch already reflects the
latest `main`, so no merge/rebase is needed and every code reference below is valid against
current `main`. Alembic head is `3a7e120d22d1` and stays there — this feature needs no
migration.

## Context

Merging resources in Stitch is implemented as **repointing**: merging A and B creates a
brand-new resource C and sets `repointed_id = C.id` on A and B. Nothing is ever
hard-deleted ([`apply_resource_merge`](deployments/api/src/stitch/api/db/og_field_resource_actions.py:307),
new resource at :349, repoint loop at :355). Repointing always targets a **brand-new row**
and every merge input must itself be unrepointed, so the `repointed_id` graph is an acyclic
forest — no resource can ever point back into a cycle.

Today a request for a merged-away resource does **not** 404. The single-resource fetch
([`get`](deployments/api/src/stitch/api/db/og_field_resource_actions.py:121)) selects purely
`WHERE ResourceModel.id == id` with **no** `repointed_id IS NULL` filter, so the row is
found — but its data/source hydration goes through `construct_base_query_statement`, whose
CTE filters `repointed_id IS NULL` ([queries.py:138](deployments/api/src/stitch/api/db/queries.py:138)).
The result is a **"null shell"**: HTTP 200, `id` set, every field `None`, empty
`source_data`. The user lands on a blank-but-successful page.

The database *knows* where A went, but nothing surfaces it: `resource_model_to_entity`
computes `repointed_to` on the entity ([utils.py:188](deployments/api/src/stitch/api/db/utils.py:188)),
but all three view builders (`resource_to_view` :248, `resource_to_list_item_view` :253,
`resource_to_detail_view` :266) drop it, so the frontend receives no signal at all.

Two user-visible consequences today:

1. **`/oil-gas-fields/A` renders a blank-but-successful page** — empty `<h1>`, every field
   `—`, "No sources attached."
2. **A pending merge candidate that overlaps an approved one becomes a dead end.**
   Candidate 1 = {A,B} and candidate 2 = {B,D}, both PENDING. Approving candidate 1
   repoints B. Candidate 2's Approve is now guaranteed HTTP 400, and the message
   interpolates `repr()` on ORM objects ([merge_candidate_actions.py:63](deployments/api/src/stitch/api/db/merge_candidate_actions.py:63),
   duplicated at [og_field_resource_actions.py:334](deployments/api/src/stitch/api/db/og_field_resource_actions.py:334)),
   so the curator sees `Repointed: [<...object at 0x104f2a3d0>]` — no id, no pointer to C.
   The only exit is **Deny**, which records a human judgment that was never made.

## Product decision (confirmed with the product owner, 2026-08-27)

**Full redirect — return the new resource everywhere. No interstitial.** If resources
`123` and `124` merge into `456`, any request that resolves to `123` returns `456` instead:

- **API:** `GET /oil-gas-fields/123` and `.../123/detail` return **456's real body** at the
  `123` URL (server-side substitution), carrying a flag (`requested_resource_id`) so the
  caller can tell the returned resource is not the one it asked for.
- **Frontend:** `ResourceDetailPage` **redirects** the browser to `/oil-gas-fields/456`
  (`navigate(..., { replace: true })`). No interstitial card, no "merged record" notice.
- **Merge Review pane:** repointed member ids resolve to their terminal resource, and the
  approve-time error names the real target instead of a memory address.

The product owner is aware this can complicate curation ("what happened to A?" no longer has
a dedicated page) and has chosen to **address that only if it manifests**, rather than build
mitigation ahead of need. That decision explicitly retires the interstitial and the
speculative retire/requeue machinery from earlier drafts (see PR 2, "Deferred").

### The `requested_resource_id` flag (answers "how do we signal a redirect happened?")

Not difficult — it is the natural mechanism, and it makes the feature *simpler* than the
interstitial approach, not harder.

- Add one nullable field, `requested_resource_id: int | None = None`, to the read views
  (`OGFieldView`, `OGFieldDetailView`). When `GET /123` resolves to `456`, the body is
  `456`'s full data with `id: 456` and `requested_resource_id: 123`. A direct `GET /456`
  returns `requested_resource_id: null`. Purely additive; no enum, no migration.
- The frontend redirect keys off the id mismatch (`detailView.id !== numericId`); the flag
  is what makes the same signal available to **scripts and logs**, which a bare redirect
  cannot: a followed HTTP 3xx lands the client on `456` and *erases* the fact that it asked
  for `123`. The flag preserves it. (It also leaves room for an optional, non-blocking "you
  were redirected from 123" note later without changing the contract.)

**Why 200 + flag, not an HTTP 3xx redirect.** A `301/308` is the textbook redirect, but it
fights this stack for no benefit here:

- `packages/stitch-client` builds `httpx.AsyncClient` with no `follow_redirects`
  ([async_client.py:45](packages/stitch-client/src/stitch/client/async_client.py:45)), so
  the default `False` means the client surfaces the 3xx instead of following it — every
  consumer breaks until that changes.
- A correct `Location` needs the `/api/v1` mount ([main.py:27](deployments/api/src/stitch/api/main.py:27))
  via `url_for` + an injected `Request`.
- `response_model=` would have to be loosened, churning the schema `test_openapi.py` guards.
- A followed 3xx hands the client `456`'s body with no record of the original request — the
  flag is strictly more informative.

If a pure API-level redirect is ever wanted for `curl`/CLI ergonomics, **use `308`** (GET
semantics, no legacy method-rewriting) *and* set `follow_redirects=True` on the client — but
that is a separate, additive change; `requested_resource_id` does not block it.

## Shipping in two PRs

**PR 1 — "redirect on the resource detail path"** (ticket AC 1 + AC 2): server-side
substitution on the two single-resource read endpoints + the `requested_resource_id` flag +
a client-side redirect. Additive schema field, one shared resolution helper, one frontend
effect. No new status, no enum change, no migration, no deploy-ordering constraint.

**PR 2 — "resolve repointed resources in the Merge Review pane"** (ticket AC 3), builds on
PR 1: the merge-candidate views resolve repointed member ids, and the approve-time error
names the terminal target. The heavier retire/requeue design is **deferred** per the product
decision (kept as an appendix so the analysis isn't lost).

**Do not close STIT-418 when PR 1 merges** — AC 3 is PR 2. Consider a sub-task.

---

# PR 1 — Redirect on the resource detail path

## API: resolve to root, substitute the body, flag the request

**Reuse dead code, add no new SQL.** `ResourceModel.get_root()`
([resource.py:104](deployments/api/src/stitch/api/db/model/resource.py:104)) already
resolves an id to its terminal resource via the recursive `_root_select` /
`_parent_tree_cte` ([:135](deployments/api/src/stitch/api/db/model/resource.py:135),
[:176](deployments/api/src/stitch/api/db/model/resource.py:176)), and is **currently
uncalled** (verified: no callers in `deployments` or `packages`). PR 1 resolves exactly one
id at a time, so it just uses it. The batch resolver belongs to PR 2, where a batch is
actually needed.

**Multi-hop collapses to one hop.** `A → C → F → J` resolves `A` directly to `J`: the
recursive term walks `repointed_id` upward and `_root_select`'s `WHERE repointed_id IS NULL`
keeps only the terminal row, so chain length is irrelevant. **The database keeps the
hop-by-hop history** (`A→C`, `C→F`, `F→J` all remain as stored rows); only the *served
resource* collapses to the root. Merge history stays fully reconstructable.

### Resolution helper — do NOT put this in `get`

`og_field_resource_actions.get` ([:121](deployments/api/src/stitch/api/db/og_field_resource_actions.py:121))
is **shared with the merge write-path**, which must operate on the exact requested row.
Auto-resolving inside `get` would silently break merges. Add a **separate, read-only**
helper alongside it:

```python
async def get_resolved(
    session: AsyncSession,
    id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldResource:
    """Return resource ``id``, following repoints to the terminal (root) resource.

    Read-only endpoints use this so a request for a merged-away resource returns the
    resource it was merged into. The write-path ``get`` intentionally does NOT resolve —
    merges must operate on the exact requested row. Resolution collapses the whole chain:
    A->C->F->J returns J for a request of A. A non-repointed id returns itself.
    """
    model = await session.scalar(select(ResourceModel).where(ResourceModel.id == id))
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )
    root_id = id if model.repointed_id is None else (await model.get_root(session)).id
    return await get(session, root_id, licensed_sources=licensed_sources)
```

- Delegating to `get(session, root_id, ...)` reuses its exact loading (`selectinload`
  memberships, refresh, hydration) and its own 404 if the root vanished — no logic
  duplicated. `root_id` is always unrepointed, so hydration returns the **real** body, not a
  null shell.
- **Cost:** happy path = one extra lightweight existence `scalar` over today; redirect path
  adds `get_root`. Both negligible for a by-id fetch. If the extra happy-path query ever
  matters, fold it by having `get_resolved` reuse the model it already loaded — noted, not
  done, to keep the diff minimal.
- `resource_model_to_entity` needs **no change**: it only ever runs against `root_id` (never
  repointed), so its `repointed_to` block ([:188](deployments/api/src/stitch/api/db/utils.py:188))
  stays `None` and `Resource._no_self_reference`
  ([stitch-models/__init__.py:81](packages/stitch-models/src/stitch/models/__init__.py:81))
  is never at risk. This is a real simplification over drafts that root-resolved
  `repointed_to` inside the entity.

### The flag on the views

**`packages/stitch-ogsi/src/stitch/ogsi/model/__init__.py`** — add
`requested_resource_id: int | None = None` to `OGFieldView` (:157) and `OGFieldDetailView`
(:167). **Not** `OGFieldListItemView` (:161): list endpoints filter out repointed rows
(`_resource_universe` :337, base CTE :138), so a list row is never a redirect. Document the
field: *the id the caller requested when it differs from `id` — i.e. this resource absorbed
that one in a merge; `null` when the caller got exactly what it asked for.*

**`deployments/api/src/stitch/api/db/utils.py`** — thread the flag through the two read view
builders (optional kwarg, default `None`, so no other caller changes):

```python
def resource_to_view(resource, requested_resource_id: int | None = None) -> OGFieldView:
    view = _require_view(resource)
    return OGFieldView(
        id=resource.id, requested_resource_id=requested_resource_id, **view.model_dump()
    )
```

`resource_to_detail_view` (:266) takes the same kwarg and passes it into its
`OGFieldDetailView(...)`. `resource_to_list_item_view` is untouched.

### The router

**`deployments/api/src/stitch/api/routers/oil_gas_fields.py`** — both handlers
([get_resource :239](deployments/api/src/stitch/api/routers/oil_gas_fields.py:239),
[get_resource_detail :253](deployments/api/src/stitch/api/routers/oil_gas_fields.py:253))
switch `resource_actions.get` → `resource_actions.get_resolved` and compute the flag from
the id mismatch:

```python
res = await resource_actions.get_resolved(
    session=uow.session, id=id, licensed_sources=licensed_sources(claims)
)
requested = id if res.id != id else None
return resource_to_view(resource=res, requested_resource_id=requested)
```

`response_model` is unchanged (still `OGFieldView` / `OGFieldDetailView`); the new field is
additive. The literal routes (`/filter-options`, `/merge-candidates`, …) already precede
`/{id}`, so nothing shadows the resolved route.

## Frontend: client-side redirect

**`deployments/stitch-frontend/src/pages/ResourceDetailPage.jsx`** — `useNavigate` is
already imported (:3) and used for `← Back` (`navigate(-1)`, :572). Add `useEffect` to the
React import (:1). There is **no mount effect today** — the fetch is declarative via
`useResourceDetail` (:561). Add one effect at the top of the component, after the hook:

```jsx
// STIT-418: the API returns the merged-into (root) resource for a repointed id,
// so detailView.id can differ from the id in the URL. Redirect to the canonical
// URL. replace:true is mandatory: without it, Back returns to the old id, which
// re-resolves and redirects again, trapping Back. No cycle guard is needed beyond
// the id check — repointing always targets a brand-new row, so the chain is acyclic
// and the root never redirects again.
useEffect(() => {
  if (
    detailView &&
    Number.isFinite(detailView.id) &&
    detailView.id !== numericId
  ) {
    navigate(`/${endpoint}/${detailView.id}`, { replace: true });
  }
}, [detailView, numericId, endpoint, navigate]);
```

The redirect keys off `detailView.id !== numericId` (works even against a backend that
predates `requested_resource_id`); the flag itself is not required for the redirect. The
existing `{detailView && …}` body (:580) renders `456`'s real data for the one frame before
the URL updates — correct content, only the URL is briefly stale, and `replace` makes it
seamless. Nothing else in the page changes; `← Back` stays.

**No interstitial, no null-shell fallback.** Because the API now substitutes the real body,
the blank-page case for a repointed resource no longer exists, so the `MergedAwayNotice`
component and the empty-record sentence from earlier drafts are **dropped** — less code, not
more.

**Mock mode is pre-existing-broken and out of scope** (surface, don't fix, per AGENTS.md):
`useResourceDetailMock` ([useResources.js:291](deployments/stitch-frontend/src/hooks/useResources.js:291))
returns a raw fixture record with no `data` wrapper, so `detailView.data.name` (:584) throws
before any of this runs. Making mock mode resolve repoints (its JSON already ships chains
like `8→13→14`) is a worthwhile *separate* commit, not part of this feature.

## PR 1 tests

**Backend** — `deployments/api/tests/db/test_resource_actions.py` has a
`_create_resource_with_sources(..., repointed_to=)` helper at :36.

- **Multi-hop collapse, 3 hops not 2.** `A → C → F → J`: `get_resolved(A)` returns `J`'s
  entity (`.id == J`, real data), and intermediates resolve too (`get_resolved(C).id == J`).
  A 2-hop chain can pass an implementation that handles only one extra level; 3 hops pins
  the recursion.
- **Non-repointed id is unchanged** — `get_resolved(live).id == live`, real data, and it
  does not call `get_root` (the `repointed_id is None` short-circuit).
- **Route integration** (`tests/routers/`): `GET /{A}` and `/{A}/detail` on a repointed
  resource return **200 with `id == J`, real data, and `requested_resource_id == A`**;
  `GET /{J}/detail` returns `requested_resource_id: null`; a list row has no
  `requested_resource_id` (or it is null).
- `tests/test_openapi.py` ([:35](deployments/api/tests/test_openapi.py:35)) — assert
  `requested_resource_id` is in the `OGFieldView` and `OGFieldDetailView` component
  properties.

**Frontend** — `ResourceDetailPage.test.jsx`.

- A repointed detail (`detailView.id !== url id`) calls
  `navigate("/oil-gas-fields/{rootId}", { replace: true })` **once**.
- A live resource (`detailView.id === url id`) does **not** trigger a redirect `navigate` —
  the existing `expect(mockNavigate).not.toHaveBeenCalled()` assertions (~:601, ~:686) now
  mean "no *redirect*"; keep them for non-repointed fixtures and add the positive redirect
  assertion for the repointed fixture.
- No redirect loop: after landing on the root id, `navigate` is not called again.

## PR 1 verification

```bash
make check
```

```bash
make dev-docker
```

1. Seed A, B. `POST /api/v1/oil-gas-fields/merge-candidates` with `{A,B}`, approve → note C.
2. `curl GET /api/v1/oil-gas-fields/{A}/detail` → **200, `id == C`, real data,
   `requested_resource_id == A`**. `GET /{C}/detail` → `requested_resource_id: null`.
3. At `http://localhost:3000`, visit `/oil-gas-fields/{A}` → the URL becomes
   `/oil-gas-fields/{C}` and C's data renders; **no blank field grid**; Back returns where
   you came from (not to A).
4. **Multi-hop:** merge `{C,X}` → F, then `{F,Y}` → J. Visit `/oil-gas-fields/{A}` → URL
   lands on **J**, not C or F. `GET /{C}` and `/{F}` also resolve to J.

## PR 1 risks

1. **`get_resolved` returns a different id than requested.** This is the intended behavior,
   but it is a genuinely new read semantic — mitigated by keeping it out of the write-path
   `get`, naming it clearly, and documenting it. Reversible in one small commit.
2. **AC 3 is not addressed** — the Merge Review pane is PR 2. Don't close the ticket.
3. **No cycle protection in the recursive CTE.** Pre-existing in `_parent_tree_cte`, and
   unreachable via `apply_resource_merge` (target is always a brand-new row, inputs must be
   unrepointed) — but the risk moves from dead code onto a read path. Acyclic by
   construction; worth a one-line note in the helper.
4. **Curation visibility.** "What happened to A?" no longer has a page — accepted by the
   product owner, to be revisited only if it manifests.
5. **Pre-existing, surfaced not fixed** (per AGENTS.md): `ResourceDetailPage` is already
   broken under `VITE_USE_MOCK_DATA=true` (mock hook returns un-wrapped records);
   `ResourceModel._complete_tree_cte` remains uncalled. **Ask before deleting.**

---

# PR 2 — Resolve repointed resources in the Merge Review pane

Builds on PR 1. Nothing here is required for PR 1 to be correct. Scoped to satisfy AC 3
under the redirect decision: **show the resolved (terminal) resource, and stop leaking
memory addresses** — without the speculative retire/requeue machinery (see "Deferred").

## Batch root resolution

**`deployments/api/src/stitch/api/db/model/resource.py`**

- Extend `_parent_tree_cte` ([:135](deployments/api/src/stitch/api/db/model/resource.py:135))
  to emit `(origin_id, id)` instead of `id`. **This is the critical fix:** today the CTE
  unions the ancestors of all inputs then filters `repointed_id IS NULL`, returning the
  *set* of roots and **losing which input maps to which root**. Add `.select_from(cls)` to
  the recursive term so SQLAlchemy infers the right FROM (precedent at
  [:80 region](deployments/api/src/stitch/api/db/model/resource.py:80)). Because
  `repointed_id` is a single scalar, each origin traces one path to exactly one root;
  `union_all` stays correct and a non-repointed input self-maps.
- Add `root_id_by_resource_id(session, resource_ids) -> dict[int, int]` — batch, one query,
  mirroring the existing `source_data_by_resource_id` / `get_constituents_by_root_id`
  conventions on the same class.
- `_root_select` still works unchanged (joins on `.c.id`), so PR 1's `get_root` /
  `get_resolved` are unaffected; add a docstring line noting `_root_select` is single-id.

## API: resolve member ids + fix the error message

**`deployments/api/src/stitch/api/db/merge_candidate_actions.py`**

- Add **one** field to `MergeCandidateView` (the base view — the queue returns it, so it
  must carry the field too, not just the detail view):
  `repointed_resources: list[RepointedResourceView]` where
  `RepointedResourceView = {resource_id: int, repointed_to: int}` (terminal id). It lists
  only the members that moved; an empty list means the candidate is still fully valid. This
  is the per-member analogue of PR 1's `requested_resource_id`.
- **Must be a plain field, not `computed_field`.** `_candidate_to_detail_view`
  ([:173](deployments/api/src/stitch/api/db/merge_candidate_actions.py:173)) rebuilds itself
  from `_candidate_to_view(model).model_dump()`; computed fields appear in `model_dump()`
  but are not settable in `__init__`, so pydantic's default `extra="ignore"` would silently
  drop them from the detail response.
- Compute it **only for PENDING candidates**; terminal statuses return
  `repointed_resources: []`. An APPROVED candidate's own members are repointed at its own
  result, so uniform resolution would make every approved candidate flag itself.
- `_resolve_candidates(session, candidates)`, batched: one `root_id_by_resource_id` call
  over the union of all member ids. `GET /merge-candidates` is unpaginated, so per-candidate
  resolution would be an unbounded N+1; keep the query count constant.
- **Fix the `repr()` message** ([:63](deployments/api/src/stitch/api/db/merge_candidate_actions.py:63)):
  add a shared `repointed_merge_error(session, repointed)` in `og_field_resource_actions.py`
  (already imported by `merge_candidate_actions`) that names each id and its **terminal**
  target: `"Cannot merge a resource that has already been merged: resource 102 is now
  resource 301."` Wire it into **both** guards — the duplicate at
  [og_field_resource_actions.py:334](deployments/api/src/stitch/api/db/og_field_resource_actions.py:334)
  too (unreachable today, but the write-path backstop; leaving one leaking a memory address
  guarantees someone eventually sees it). The extra query fires only on the error path. Fix
  the message, **not** `ResourceModel.__repr__` — a repr cannot name the terminal target.

## Frontend: merge review pane

**`deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx`**

- **Stale banner** in the `<article>` banner slot, **warning** tone (nothing failed, but it
  blocks approve). One line per moved member: *"Resource 102 was merged into 301."* with
  both ids as `text-primary underline` links. Clicking the old id lands on PR 1's redirect,
  which resolves to the new resource — so the pane and the detail page tell one story.
- **Hide the whole `DecisionControls` section when a member has moved**, not disable.
  Approve is guaranteed to 400, and **Deny is equally wrong** — it records a "not the same
  field" judgment that was never made. A disabled button with no tooltip pattern in this app
  is a dead end; hiding is simpler and more honest. The banner tells the curator what
  happened and links them to the resolved resource.
- Keep `CandidateFacts` links; append `(now <link>301</link>)` in `text-ink-muted` for a
  moved member.

**`deployments/stitch-frontend/src/utils/mergeCandidateStaleness.js`** (new) — the single
place that reads the API's `repointed_resources`, so a rename is a one-file change. Exports
`readCandidateStaleness(candidate)` → `{ isStale, moves }` and `formatIdList(ids)`. Degrades
to "not stale" when the field is absent (tested).

**Fix the approve invalidation** (the approve branch of the review page) — currently only
the two merge-candidate keys are invalidated, so after an approve an overlapping candidate's
cached detail can still serve stale `repointed_resources` — a direct cause of the bug being
fixed. Since every relevant key is prefixed by `[endpoint]`, replace the two calls with
`invalidateQueries({ queryKey: resourceKeys.all(ENDPOINT) })` on the **approve** branch
only. (This is also what makes PR 1's redirect show correct data immediately after a merge.)
Deny keeps its narrow invalidation.

## PR 2 tests

- **The origin-column trap** — `root_id_by_resource_id` over `{A(→C→F→J), B(→C→F→J),
  D(live)}` yields `{A:J, B:J, D:D}` against real SQL.
- **The N+1 guard** — two candidates, assert `root_id_by_resource_id` awaited **once** with
  the union of ids.
- **The cross-candidate case (uncovered today)** — candidate1 {A,B}, candidate2 {B,D},
  approve 1, then: candidate2 reports the move on both the detail *and* the queue row;
  approve → 400 containing `str(B)` and `str(C)` and **not** `"object at 0x"`, still PENDING
  after.
- **An approved candidate reports no staleness** — pins the PENDING-only rule.
- `deployments/api/tests/db/actions/test_merge.py` is a 6-line stub — fill it with **one**
  case: an already-repointed input raises with the actionable message.
- **Frontend:** two mandatory mechanical fixes first, or existing merge-review tests fail at
  import — ensure the `vi.mock("../queries/api")` factory and a `usePermissions` mock exist
  as the suite already requires. Then: stale banner names both ids as links; Approve/Deny
  hidden when stale; a payload with no `repointed_resources` renders exactly as today
  (compat guard); approve invalidates `["oil-gas-fields"]`. Pure-function suite for
  `mergeCandidateStaleness.js` in the style of `candidateCompare.test.js`.

## PR 2 verification

```bash
make check
```

```bash
make dev-docker
```

1. Seed A, B, D. Create candidates `{A,B}` and `{B,D}`. Approve the first → C.
2. `GET /api/v1/oil-gas-fields/merge-candidates` → candidate 2's **queue row** carries
   `repointed_resources: [{resource_id: B, repointed_to: C}]`.
3. `POST .../merge-candidates/{c2}/approve` → 400 naming B and C, **no `object at 0x`**;
   candidate 2 still PENDING.
4. Merge Review → select candidate 2 → warning banner naming B → C, no Approve/Deny;
   clicking B redirects to C.

## PR 2 risks

1. **`GET /merge-candidates` is still unpaginated.** Query count stays constant, but the
   `IN (...)` bind lists grow with total member count. Paginating the queue is the real fix
   — follow-up ticket.
2. **No new status, no new endpoint, no forward-only deploy constraint** — a deliberate
   consequence of deferring retire/requeue (below). PR 2 is purely additive and
   rollback-safe.
3. **Pre-existing, surfaced not fixed:** after this PR, `get_root`, `_root_select`,
   `_parent_tree_cte`, and the new batch resolver are four near-identical recursion helpers;
   `_complete_tree_cte` stays uncalled. **Ask before deleting any of it.**

## Deferred (build only if it manifests) — retire / requeue stale candidates

Per the product decision, the following is **explicitly out of scope** for now and recorded
so the analysis isn't relost. Ship it only when the stale-candidate dead end (a curator
whose only exit is a false Deny) actually bites a real reviewer.

- A new terminal status `SUPERSEDED` (pydantic `StrEnum`; no migration — `status` is a plain
  `String(20)`, [model/merge_candidate.py:25](deployments/api/src/stitch/api/db/model/merge_candidate.py:25)),
  a `POST /merge-candidates/{id}/supersede` action mirroring deny, and a one-click "retire
  and requeue the resolved pair" button (`resolved_resource_ids`, `resolved_candidate_id`,
  the degenerate-collapse `< 2` rule, and the two-write partial-failure recovery flow).
- **Why deferred:** it is the only part of the design that is not purely additive. A
  `SUPERSEDED` row cannot be validated by a previous API version, forcing an API-before-
  frontend deploy with **no rollback after the first retire**. It also changes three
  user-visible `create_merge_candidate` error strings ([:264](deployments/api/src/stitch/api/db/merge_candidate_actions.py:264))
  and needs a `merge-candidate:create` Auth0 role grant to be visible. That is exactly the
  "build ahead of need" the product owner chose to avoid. PR 1's redirect + PR 2's fixed
  error message already turn the dead end from an invisible blank page into a clear "resource
  102 is now resource 301," which is the immediate harm reduction.
