# Phase A — Precomputed current-state read model (STIT-766)

Make oil/gas-field `list` and `filter-options` fast by serving already-resolved, permission-scoped
state from a reconstructable derived table, instead of re-running coalescing per request. The live
coalescer stays as the fallback, so nothing external to the core changes. **Only** the read model —
no priority-store consolidation (Phase B).

- **Base branch:** `design/db-state-refactor` (not `main`, not the #290 branch). Merge `main` in if stale.
- **Reference:** PR #290 (`refactor/db-mv`) is a working implementation + source of scars — re-derive
  cleanly here, don't cherry-pick wholesale. **Design/discussion:** #279. **Perf validation:** #290.

---

## Context

`list` / `filter-options` repeatedly resolve the same coalesced state (membership → priority →
`ROW_NUMBER()` winner-pick → pivot), which scales ~linearly with data and dominates latency. #290
validated that precomputing the resolved state is the win: at ~prod scale, `list` ~14–21× and
`filter-options` ~10–21× faster, with response parity. Keep that; nothing else.

## Goals

1. Serve `list` / `filter-options` as cheap reads over resolved state, not per-request winner-selection.
2. Don't change answers or permission semantics — the live coalescer stays the definition of correct.
3. Read model is purely derived, disposable, and rebuilt *from the live coalescer* (no second ranking impl).
4. Rebuild/repair are ordinary ops; dropping/emptying the table loses nothing.

## Non-goals

Phase B / priority-table changes; serving `detail`/`GET {id}` or `source_data` from the model; any
REST/wire/frontend change; authz-in-DB / RLS / permissions-as-DB-state (#279 debate); triggers / CDC /
outbox; variant dedup; a general caching framework; speculative broad indexing before plan evidence.

**Related (NOT a dependency):** the membership uniqueness/dedup + `(resource_id, status)` index is a
separate in-flight DB-cleanup thread. Do **not** reimplement it; consume it if it's already in the
base. Phase A is correct and mergeable without it (the read model mirrors live; that index is a
live-path perf item). It is not a merge gate.

---

## Invariants (the contract — prefer the simpler implementation that preserves these)

1. **Derived:** every value is reconstructable from authoritative tables + current coalescing rules.
2. **Disposable:** deleting the read-model tables loses no authoritative data.
3. **Same answer:** for each cached profile, materialized state == the live coalescer for that *exact* source set.
4. **Exact permissions:** cached state is used only when the grant set *exactly equals* a supported profile; partial/extra/unknown/unscoped grants go live — never broadened/narrowed to a nearby profile.
5. **Listability == live:** the materialized resource set follows the live `list` eligibility rules exactly; don't invent a separate "active membership" definition.
6. **Repointed resources disappear** from cached state.
7. **Write coherence:** every app-owned mutation that can change a cached answer refreshes the affected resource in the same unit of work.
8. **Incomplete state is invisible:** a partial/failed/in-progress rebuild is never a fast-path source (explicit readiness flag, below).
9. **Live path stays real** — executable, tested, used for fallback + parity.

---

## Locked choices

| Area | Choice |
|---|---|
| Storage | Regular table `og_field_resource_state` (+ tiny readiness status record) |
| Maintenance | Explicit app refresh calls inside the authoritative write transaction |
| Concurrency | Pessimistic `FOR UPDATE` lock on the resource row before targeted recompute |
| Read endpoints | Fast path for `list` + `filter-options` only; detail stays live |
| Record shape | Typed columns per flattened field + `provenance` JSON |
| Permission matching | Exact match against four explicitly enumerated profiles; else live |
| Variant storage | One row per `(resource_id, permission_mask)` per profile; no dedup |
| Winner logic | Existing live coalescer; no second ranking impl |
| Readiness | Explicit `ready` flag; never infer readiness from "table non-empty" |
| Full rebuild | Required deploy step, decoupled from Alembic, batched, gated by the flag |
| Clear strategy | Portable DELETE first; PG `TRUNCATE` is a later optimization if needed |
| `--since` rebuild | Optional; only if a trustworthy cross-mutation watermark exists |

---

## Permission profiles

Keep the supported set **explicit**, not derived from the live source registry, so a new source key
fails closed (falls to live) until deliberately added.

- `PUBLIC_SOURCES = {gem, rmi, llm, alb, bc, nor}` (enumerate literally).
- Restricted: `wm`, `ccr`.
- **Drift test:** assert `frozenset(get_args(OGSISrcKey)) == PUBLIC_SOURCES | {wm, ccr}` — adding any
  source key trips it, forcing a conscious revisit rather than silently widening every cached profile.

Four exact profiles → masks:

| Mask | Exact grant set |
|---:|---|
| 0 | `PUBLIC` |
| 1 | `PUBLIC ∪ {ccr}` |
| 2 | `PUBLIC ∪ {wm}` |
| 3 | `PUBLIC ∪ {wm, ccr}` |

`db/read_model/permissions.py`: declare the four `frozenset` profiles; `read_model_mask(sources)` →
mask only when `frozenset(sources)` **exactly equals** a profile, else `None` (partial, extra,
unknown, or `None`); `visible_sources_for_mask(mask)` → the exact set. No subset/floor/closest matching.

---

## Schema

`db/model/og_field_resource_state.py`:

```text
og_field_resource_state
  resource_id      BIGINT   FK -> og_field_resources.id ON DELETE CASCADE
  permission_mask  SMALLINT 0..3
  <OilGasFieldBase fields>  typed columns (reuse ATTRIBUTE_KINDS / PORTABLE_*)
  provenance       JSON/JSONB  field -> winning source key or null
  PRIMARY KEY (resource_id, permission_mask)
```

- Export in `db/model/__init__.py`; drift-guard the value-column set against `ATTRIBUTE_NAMES`.
- Store `provenance` as JSON (returned with list items; never a filter/sort dimension).
- Do **not** store the raw per-source candidate graph (`source_data`).
- Store all four rows per eligible resource even when two masks resolve identically.

**Readiness status** (tiny, disposable operational metadata — not domain state):

```text
og_field_resource_state_status
  key         TEXT PK      # singleton, e.g. "resource_state"
  ready       BOOLEAN NOT NULL
  rebuilt_at  TIMESTAMPTZ NULL
```

Migration initializes `ready = false`. Fast-path reads require `ready = true`. Targeted write-path
refreshes may populate rows while `ready = false`, but readers stay live until a full rebuild sets it
true. This replaces the unsafe "≥1 row ⇒ ready" heuristic, whose real failure is: write hooks populate
a *few* resources between migration and the first rebuild, and an EXISTS check would then serve a
partial list.

**Eligibility:** reuse the live `list` eligibility predicate (the base branch's `_resource_universe`
or equivalent) for which resources get rows — don't reinvent "non-repointed + active membership."
Parity-test the edge case of a current resource with zero active memberships/values so the cache can't
redefine listability.

### Indexes (best guess now; tune empirically near the end)

PK `(resource_id, permission_mask)`; `(permission_mask, resource_id)` for single-profile scans;
`(permission_mask, <field>)` for each `FILTER_OPTION_FIELDS` column; and one mask-leading index for the
list's actual default sort once confirmed on the base. Don't index every sort/filter combo up front —
near the end, run `EXPLAIN (ANALYZE, BUFFERS)` / the #290 load shape and adjust. Index tuning may be
split into a small follow-up if correctness is otherwise ready; record deferred findings.

---

## State computation (`db/read_model/state.py`)

```python
async def refresh_resource_state(session, resource_id) -> None: ...
async def refresh_resource_states(session, resource_ids) -> None: ...
async def remove_resource_state(session, resource_id) -> None: ...
async def rebuild_all_resource_state(session) -> None: ...
async def refresh_changed_since(session, timestamp) -> None: ...   # optional, see --since
```

**Reuse the live coalescer.** For each profile: pick its exact visible-source set → call the narrowest
reusable live layer (`coalesce_resources` / `coalesced_winner_rows` / base equivalent) → project
winners to typed columns + provenance → replace that resource's rows. The coalescer is the oracle for
both fallback and materialized state; this is the key guard against drift.

**Targeted replace (per resource):** take `SELECT 1 FROM og_field_resources WHERE id=:id FOR UPDATE`
*before* reading the data to recompute; then delete+reinsert that resource's rows in the caller's
transaction. If the resource is no longer eligible, delete and insert nothing. The lock is a small
correctness guard (serializes concurrent writers to the same resource so their refreshes can't
interleave into a lost update / PK collision), not a concurrency subsystem; it's a no-op under SQLite.
For multi-resource ops (merge), lock resource rows in **stable id order** to avoid deadlocks. No
field-level incremental mutation — whole-resource recompute is simpler and cheap at this scale.

---

## Write-path hardening

Wire refresh into the base-branch equivalents of: resource create; source attach
(`_attach_source_models` / `attach_sources_to_resource`); per-field priority change
(`set_field_source_priority`); merge/repoint (`apply_resource_merge` — remove repointed originals,
build the new current resource, lock in id order).

Then **inventory** all writes (API/ETL/LLM/review) that can change: a source value for an
already-attached source; membership creation/status; default or per-resource priority; repoint/merge
state. Each must call a refresh or be proven unable to affect cached state; put the inventory in the PR
notes. Call out the one shape per-resource hooks don't cover: an **in-place edit of a source value**,
which affects *every* resource that source is attached to. We don't do this today — the inventory must
confirm it; if ever added, it must refresh all resources linked to that source (via memberships).

**Transaction rule:** refresh in the same `AsyncSession` as the authoritative write — they commit
together. No triggers/cross-process machinery in v1 beyond the per-resource lock.

---

## Read path

**`list`** (`query(...)`): map `licensed_sources` to an exact mask; if no mask **or** not `ready` →
live implementation unchanged; else filter/sort/count/page directly against the table for that mask and
hydrate `OGFieldListItemView` from typed columns + provenance (no ranking window). Keep the live impl
as a clearly named helper.

**`filter-options`**: same gate; else DISTINCT non-null per `FILTER_OPTION_FIELDS` column for the mask,
preserving output shape/order.

**Observability:** preserve the established `named_query` labels (`resources.count`,
`resources.list_ids`, `resources.list_hydrate`, `resources.filter_options`) — observability tests
assert exact label sets. Keep the readiness lookup *out* of that label contract unless you
intentionally update those tests.

**Detail / single-resource:** stays live (needs `source_data`; already cheap; not the bottleneck).

---

## Migration, rebuild, readiness

**Alembic migration (schema only):** create the state table + readiness status (init `ready=false`) +
initial indexes; leave priority tables untouched; do not run the app coalescer; downgrade per repo
convention.

**Full rebuild** — a **required deploy step, not inside the Alembic revision** (the revision is sync
and the coalescer is async; and reimplementing coalescing in SQL would be a second ranking impl →
breaks invariant 3). With the readiness flag it need not be one giant transaction:

1. set `ready=false`, commit → all reads immediately go live;
2. clear derived rows (portable DELETE; TRUNCATE later if it's a bottleneck);
3. enumerate eligible resources via the live list predicate;
4. rebuild in bounded batches (lock resource rows in id order, compute four profiles via the coalescer, replace, commit per batch);
5. integrity-check (four masks per resource, no repointed rows);
6. set `ready=true` + `rebuilt_at`.

A failure leaves `ready=false` → reads stay live; partial rows are harmless (invisible + overwritten on
re-run). Serialize full rebuilds via the status singleton.

**CLI** `db/read_model/rebuild.py`: `python -m …rebuild` (full); `--ids 1 2` (targeted repair, uses the
same per-resource lock + recompute, safe while ready); `--since <ts>` **only if** a watermark provably
covers every mutation class (membership/priority/merge/source) — otherwise omit rather than ship a
misleading one.

---

## Deployment sequence

1. From `design/db-state-refactor`, apply the schema migration (`ready=false`).
2. Deploy app code (write hooks + fast path) — reads stay live because not ready.
3. Run the required full rebuild; it flips `ready=true` only on complete success.
4. Verify row count ≈ `4 × eligible_resources`; smoke-test all four profiles + one fallback; compare
   cached vs live on a sample; inspect named-query timings / plans; tune or defer indexes on evidence.
5. The live fallback stays permanently — it's permission-safety + recovery, not migration scaffolding.

---

## Scars from #290 (don't rediscover)

- It's **`ccr`, not `cc`**; **`nor`** exists; eight keys total.
- Read model is a plain table → the SQLite `is_view` test-fixture handling is irrelevant.
- Typed columns beat one JSON blob (filter/sort + indexed filter-option DISTINCTs); a jsonb-record
  prototype was larger/slower with no better search.
- `provenance` (field → winning source key) is required by list items.
- `source_data` can't be rebuilt from winners — keep detail live.
- Reuse the coalescer per profile so ranking can't drift; drift-guard columns vs `ATTRIBUTE_NAMES`;
  reuse `ATTRIBUTE_KINDS` / `PORTABLE_*`.
- Round-trip tests must cover JSON/list (owners/operators) and numeric fields, not just text.
- Preserve the `named_query` labels.

---

## Testing (comprehensive on semantic risk, not exhaustive)

1. **Profiles:** each exact set ↔ mask; partial public, extra/unknown key, and `None` → live; the
   source-universe drift test trips on a new key.
2. **Builder parity + round-trips:** deterministic fixture (all 8 families; competing values/default
   priorities; per-resource overrides; nulls; JSON/list + numeric fields; merged resources; a current
   resource with zero active values) → stored values + provenance == fresh live coalescing, all four
   profiles.
3. **Read parity:** cached == live per profile across default + explicit paging, each sort/dir, `q`,
   each filter, combined filters, total count, and the full `filter-options` response. Cover each
   branch/operator at least once (not the full Cartesian product).
4. **Readiness/fallback:** not-ready + zero rows → live; **not-ready + some write-populated rows →
   still live** (the partial-population guard); failed rebuild never flips ready; ready enables the
   fast path; unsupported profiles stay live even when ready.
5. **Mutation sync:** for each inventoried path (create, attach, reprioritize, merge/repoint,
   membership-status if exposed, and an in-place attached-source-value change via a test helper even
   though prod doesn't do it) cached state after commit == fresh recompute; merged-away resources lose
   rows.
6. **Concurrency (Postgres):** two concurrent refreshes/mutations for the same resource serialize on
   the resource row and end matching authoritative data; unit-test stable id lock ordering for merge.
   Don't fake row locks on SQLite.
7. **Rebuild/recovery:** full rebuild from unready; idempotent; readiness transitions; delete/corrupt
   rows → full rebuild repairs; `--ids` touches only requested; `--since` only if implemented (prove
   its watermark covers all mutation classes).
8. **Schema/drift + perf:** columns aligned with flattened attributes; exactly four masks per eligible
   resource post-rebuild; no repointed rows while ready. Near the end, rerun the #290 load shape —
   verify no global winner-selection on the fast path, filter-options is a mask-scoped DISTINCT,
   order-of-magnitude win holds, and initial indexes are used; apply evidence-backed index changes or
   defer them explicitly.

---

## Commit sequence

1. `feat(api): add resource-state read model schema` — model + readiness status + export + schema
   migration + explicit profiles/helpers + source drift guard + initial indexes + profile/schema tests.
2. `feat(api): build and rebuild resource read state` — `state.py` (reuse coalescer) + per-resource +
   stable-order locks + targeted refresh/remove + batched full rebuild + readiness transitions + CLI
   (`--ids`; `--since` only if sound) + builder/round-trip/readiness/rebuild tests.
3. `feat(api): refresh resource state on mutations` — hook create/attach/reprioritize/merge + mutation
   inventory (in PR notes) + mutation-vs-recompute parity tests + concurrency test.
4. `perf(api): serve resource list reads from precomputed state` — exact-profile + readiness fast path
   for list and filter-options, live fallback preserved, wire models + named-query labels unchanged,
   read-parity + fallback tests.
5. `docs(api): document resource-state rollout and verification` — `make check`, load/query-plan
   checks, evidence-backed index tuning, deploy/rebuild/verify docs, deferred findings.

---

## Definition of done

- Based on `design/db-state-refactor`; `og_field_resource_state` holds only reconstructable state.
- Four exact profiles explicit + tested; any non-exact/unknown/unscoped grant uses live; source-universe
  drift test in place.
- State computed via the live coalescer; listability matches the live list path (incl. the empty-
  resource edge).
- Targeted refreshes use the per-resource lock + same transaction; all authoritative mutation paths
  inventoried and hooked-or-proven-irrelevant (incl. the in-place-source-edit contract test).
- Readiness flag prevents partial/failed/in-progress rebuilds from serving; full + `--ids` rebuilds
  implemented and tested; corruption → rebuild restores parity; `--since` sound or omitted.
- `list`/`filter-options` use the model only when ready; unsupported/not-ready use live; detail stays
  live; priority tables unchanged; DB-cleanup work not duplicated.
- Parity (values/provenance/JSON/numeric/null/merge/permission), readiness, mutation, and recovery
  tests pass; named-query labels intact; `make check` passes; load/query-plan verification done with
  index changes applied or explicitly deferred.

## Deferred

Phase B; detail-from-model; authz-in-DB / permissions-as-view / `og_field_attributes`; variant dedup;
triggers / CDC / outbox / drift reconciliation; staging-swap rebuilds; revisiting the representation if
restricted dimensions grow past ~4–5 (>~32 masks); further production-plan-driven index tuning.
