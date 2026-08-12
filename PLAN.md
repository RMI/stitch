# STIT-576 — Hide approved merges from the review queue by default

## Context

Reviewers open the Merge Review queue to do pending work, but the queue currently
renders every merge candidate ever created — `PENDING`, `APPROVED`, and `DENIED`
alike — ordered newest-first and unpaginated. As candidates accumulate, finished
decisions crowd out the work that still needs a human, and there is no way to
narrow the view.

STIT-576 asks for the sensible default: show pending work, with a visible control
to bring the finished items back when needed.

This is deliberately the narrow slice. **STIT-577** owns the full server-side
filters-and-sorting story (state, linkage date, approval date, approver) and
**STIT-578** owns search. This plan does not pre-commit their API design.

**Outcome:** the queue opens showing only work that needs a decision; a checkbox
reveals the reviewed items; the header counters keep reporting the true totals.

## Decisions made

| Decision | Choice | Why |
|---|---|---|
| Where filtering happens | Client-side | Endpoint is unpaginated and already returns every row, so no round trip is saved. Critically, the header Pending/Reviewed/Total counters are derived from the *full* list — server-side filtering would break two of three and force a second query or a counts endpoint. |
| Default hidden set | `{APPROVED, DENIED}` | Both are terminal decisions; the story's intent is "only see pending work". |
| Deny-list vs allow-list | Deny-list (hidden statuses) | More statuses are coming. A deny-list shows an unrecognized new status; an allow-list would silently hide it. Accidentally hiding pending work is the worse, quieter failure. |
| Control shape | Single "Show reviewed" checkbox | Satisfies the AC at current scale (3 statuses, effectively binary). State is still a status *set*, so swapping in `FilterDropdown` when a 4th status lands touches only the control. |
| On approve/deny | Keep the decided row pinned | Preserves confirmation that the decision landed and keeps the review pane's reviewed state reachable. |
| Persistence | Plain component state | Page has no URL state today. Defer to STIT-577/578, which need it for shareable filters and search. |

## Changes

### 1. New — `deployments/stitch-frontend/src/constants/mergeCandidateStatus.js`

Follows the existing `src/constants/fieldMeta.js` / `sourceMeta.js` pattern.

There is currently **no frontend status enum** — `"PENDING"` appears as a bare
literal in six places on the page. A canonical list is a prerequisite for any
status-set-shaped filter, and it is what makes this liftable to an API param later.

Exports:

- `MERGE_CANDIDATE_STATUS` — `{ PENDING, APPROVED, DENIED }`, mirroring
  `MergeCandidateStatus` in [entities.py:149](deployments/api/src/stitch/api/entities.py:149)
- `DEFAULT_HIDDEN_STATUSES` — `[APPROVED, DENIED]`
- `getStatusLabel(status)` and `getStatusClasses(status)` — moved verbatim from
  [MergeCandidateReviewPage.jsx:20-36](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:20).
  Keep both fallback branches intact: `getStatusClasses` already returns neutral
  classes for unknown values, and `getStatusLabel` already passes unknowns through.
  That is exactly the new-status tolerance the deny-list depends on.

Scope boundary: extract the status vocabulary only. The overlap between the
page-local `StatusBadge` and the shared `src/components/StateBadge.jsx` is
pre-existing and out of scope — do not unify them here.

### 2. `deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx`

- Import the constants; delete the now-orphaned local `getStatusClasses` /
  `getStatusLabel`. `StatusBadge` stays on the page, now sourcing from constants.
- Add `const [hiddenStatuses, setHiddenStatuses] = useState(DEFAULT_HIDDEN_STATUSES)`.
  Hold the **set**, not a boolean — the checkbox toggles between
  `DEFAULT_HIDDEN_STATUSES` and `[]`. This is the shape that survives a later
  swap to a per-status control or an API param.
- Derive `visibleCandidates` (memoized): candidates whose status is not hidden,
  **plus** the currently-selected candidate regardless of status. That single
  exception implements the pinning decision — the row you just decided stays put,
  and it drops out on the next reload or filter change.
- Keep `pendingCount` / `reviewedCount` / Total reading the **unfiltered**
  `candidates` ([:416-420](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:416)).
  This is the whole reason for filtering client-side; do not change it.
- Point `QueuePanel` at `visibleCandidates`.
- Change default selection ([:398-401](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:398))
  to pick from `visibleCandidates` so a hidden row is never auto-selected.
  Leave the render-time-selection approach and its comment alone.
- Auto-advance in `handleReview` ([:454](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:454))
  needs no change — it seeks the next `PENDING`, which is never hidden by default.

### 3. `QueuePanel` — control and empty states

- Render the checkbox in the panel header beside the `<h2>Queue</h2>`
  ([:94-96](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:94)),
  where it is contextually adjacent to what it filters. Follow the inline
  checkbox markup at
  [EntityLinkagePage.jsx:278-286](deployments/stitch-frontend/src/pages/EntityLinkagePage.jsx:278)
  (`className="accent-primary"` with a `<label>` wrapper).
- Label: "Show reviewed", with the hidden count when non-zero.
- **Two distinct empty states.** Today there is one message, "No merge candidates
  to review." ([:119-121](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.jsx:119)).
  Keep it for a genuinely empty list, and add a separate message for "list is
  non-empty but everything is filtered out" — otherwise a reviewer with a cleared
  queue cannot tell an empty backlog from a hiding filter. The second message
  should name the hidden count and sit next to the checkbox that undoes it.

## Tests

`deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.test.jsx` —
**existing tests will break, by design.** The fixtures are a PENDING id 11 and an
APPROVED id 12 ([:33-46](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.test.jsx:33)),
and the APPROVED row is now hidden on first paint. Affected tests must toggle
"Show reviewed" on before asserting. The clearest casualty is the STIT-575
regression test at
[:164](deployments/stitch-frontend/src/pages/MergeCandidateReviewPage.test.jsx:164),
which asserts the APPROVED row renders "APPROVED" — that behavior is unchanged
and the test should survive with a toggle step, not be weakened.

Note rows are located by name text (`findByRole("button", { name: /Bergan/ })`),
not test ids, so queue markup changes ripple through this file.

New cases:

1. Default queue omits `APPROVED` and `DENIED`, includes `PENDING`.
2. Toggling "Show reviewed" reveals them; toggling back re-hides.
3. Header Pending / Reviewed / Total are identical with the filter on and off.
4. A candidate decided during the session stays in the queue with its new badge.
5. All-hidden empty state shows the filtered message, not "No merge candidates".
6. An unrecognized status value renders in the default queue (locks in the
   deny-list behavior that the "more statuses coming" requirement depends on).

New `src/constants/mergeCandidateStatus.test.js` for the label/class helpers
including unknown-value fallbacks, following `src/constants/fieldMeta.test.js`.

No backend changes, so no API tests.

## Verification

```bash
cd deployments/stitch-frontend && npx vitest run src/pages/MergeCandidateReviewPage.test.jsx src/constants
```

Then the full suite from the repo root:

```bash
make check
```

Manual pass — the mock hook returns `[]`, so this needs the real stack:

```bash
make frontend-dev
```

At `http://localhost:3000/merge-candidate-review`, confirm: queue opens with
pending only; Reviewed and Total still report the true counts; "Show reviewed"
reveals the finished rows with correct badges; approving a candidate leaves it
visible with an APPROVED badge while selection advances to the next pending; and
with every candidate reviewed, the queue explains that rows are hidden rather
than claiming there is nothing to review.

## Out of scope

- Server-side `status` query param — STIT-577.
- Sorting, search, URL/shared filter state — STIT-577, STIT-578.
- Pagination for the merge-candidate list (pre-existing gap: the endpoint returns
  every row unpaginated).
- Unifying `StatusBadge` with the shared `StateBadge`.

## Pre-existing issues found, not addressed

- [API_REFERENCE.md:139](deployments/api/API_REFERENCE.md:139) documents a
  `merge-candidates/{id}/preview` endpoint that no longer exists in any router.
- `deployments/api/scripts/api_doc.py check` is not wired into any Makefile target
  or CI workflow, which is why the above went stale.
- `getMergeCandidates` / `getMergeCandidate` in `src/queries/api.js` have no unit
  tests, and `src/queries/resources.test.js` has no merge-candidate cases.
