# STIT-766 — Current-state read model: design proposal

**Status:** draft
**Author:** Michael Barlow
**Reviewer:** John McGrath
**Jira:** [STIT-766](https://rmi1.atlassian.net/browse/STIT-766) (epic [STIT-689](https://rmi1.atlassian.net/browse/STIT-689))
**Created**: 2026-09-17

## 1. Objective

Design a database architecture and application logic to serve the key Stitch endpoints with lower latency.

## 2. Background

### Problem

The `list`, `filter-options`, and `detail` endpoints all rebuild the same thing on
every request: one coalesced, flat row per resource that represents the current top-level "state".
`queries.py` does this by joining membership → resource → default priority → source → value rows,
left-joining per-field overrides, ranking candidates with a four-key `ROW_NUMBER()`
window, and then pivoting the winners into columns with `max(case(...))` per field.

Combined with serializing to/from Pydantic models, this has led to poor response times that
negatively impact user experience. Furthermore, given that our entire db is less than 100MB
in size, this raises questions about our overall db design and access patterns.

### Observations

With the newly added attribute-level priority feature ([STIT-494](https://rmi1.atlassian.net/browse/STIT-494)), we now
have a more deterministic and bounded way to establish the different variations we
display for a flat resource. Our permissions model only has 2 restricted options: `wm` and `cc`.
All the remaining sources are public, and ALL users have read permissions for them.

> [!NOTE]
> It was more straightforward to treat these individually when implemented, but reviewing our permissions model
> may help simplify in the future. However, it's not strictly necessary for this work.

If we think of the set of `llm`, `rmi`, `bc`, `alb`, and `gem` as a single `public` visibility.
Then there are some fairly significant implications in how our coalescing logic actually
plays out. For any given attribute on a coalesced resource, users will see at most 3
possible options: `wm`, `cc`, and the highest priority `public` source. To illustrate,
see the following scenarios for a resource's `latitude` data:

- priorities: `wm`, `cc`, `gem`, `bc`
  - user with `wm + cc` sees `wm`
  - user with `wm` sees `wm`
  - user with `cc` sees `cc`
  - remaining users see `gem`
- priorities: `wm`, `cc`, `gem`, `rmi`, `llm`, `alb`
  - user with `wm + cc` sees `wm`
  - user with `wm` sees `wm`
  - user with `cc` sees `cc`
  - remaining users see `gem`
- priorities: `cc`, `gem`, `wm`, `bc`
  - user with `wm + cc` sees `cc`
  - user with `cc` sees `cc`
  - all remaining users (including `wm` viewers) see `gem`
- priorities: `bc`, `cc`, `wm`, `gem`
  - all users see `bc`
- priorities: `bc`, `gem`, `cc`, `wm`
  - all users see `bc`

For any view or operation that interacts only with the flattened representation of a resource:

- we only need to store/cache up to the first public source in the priority list
- a resource attribute has at most 3 variations: `wm`, `cc`, and `public`
- an entire coalesced resource has **at most 4 possible variations** depending on user permissions
  and attribute priorities:
  - `public`: all attributes have a public source as the highest priority
  - `public + wm`: 1 or more attributes has `wm` as highest priority and all next-highest priorities are public
    - said another way, all top 2 priorities are either `wm` or `public` and at least 1 is `wm`
  - `public + cc`: 1 or more attributes has `cc` as highest priority and all next-highest priorities are public
    - all top 2 priorities are either `cc` or `public` and at least 1 is `cc`
  - `public + wm + cc`: at least 1 attribute where `wm` is highest **AND** 1 attribute where `cc` is highest
    - Note: `wm + cc` must see different data from both `wm` and `cc` individually

Thus, whatever structure we use here is bounded by at most 4 x the number of top-level (unmerged) resources: 1 variant for each
possible licensed representation.

> [!NOTE]
> One caveat here is that the number of possible variants grows exponentially with the number of distinct licenses:
>
> - 2 licensed sources = 4 variants
> - 3 licensed sources = 8 variants
> - 4 licensed sources = 16 variants
>
> so even if we add 2 proprietary sources, this structure grows to a max of 16 x the number of top-level (unmerged) resources.
> I don't see this as a real issue even in the long term. How many licensed sources are even realistic? 6? 10? Even at 10
> proprietary sources, the view/table would be 2^10 = 1024 x resources. The upper bound of **all** named fields is probably
> somewhere in the ~65k range, so ~65M rows is still manageable...if we'd ever even get close to that.

## 2. Goals and non-goals

**Goals**

- Serve `list` and `filter-options` with <100ms latency
- Give the database one unambiguous stored answer to "what is the value for each attribute of a resource for a user with X permissions"
- Express the invariants declaratively in schema, so the sync/refresh mechanism has lower/zero risk regarding correctness
- Preserve the public REST surface and today's behavior

**Non-goals**

- A general permission-based solution that accounts for all future/unknown licensed and public permissions
- The details of the sync mechanism. See §6.
- Redesigning the permission model.

## 3. Proposal

Part of the goal is to trade application complexity for schema complexity. Making schemas more complex
but in a way that enables tighter constraints and simpler queries (i.e. through mostly joins) frees
out application code from being the enforcer of invariants.

### Attributes table

Add `og_field_attributes` table:

- id: primary key
- name: attribute name
- (optional) description
- (optional) type: text, int, float, json, etc...

Priority rows and EAV rows reference `og_field_attribute.id`

### Single priority table

Replace the two-table priority split with a single table at the
`(resource, attribute, source record)` grain, and use defaults when
writing new data rather than as a SQL fallback rule.

- Add `og_field_resource_attribute_priority` table.
  - resource_id: fk to resources
  - attribute_id: fk to `og_field_attributes`
  - source_id: fk to `oil_gas_field_sources`
  - priority: int
  - is_curated: bool (false if default, true if set by user)
- Drop `og_field_source_priority` and `og_field_resource_source_priority`.
- On resource or source creation, write explicit priority rows for every attribute
  the source has a value for, seeded from the existing `SOURCE_PRIORITY` tuple in
  `stitch.ogsi.model`.
- Add constraints:
  - unique priority across resource and attribute: no 2 sources for a resource + attribute can have the same priority
    `UNIQUE (resource_id, attribute_id, priority)`
  - priority > 0
  - fk to memberships on resource_id, source_id: ensure source is attached to resource
  - fk to ``

### Benefits

#### Simpler, faster SQL

Provenance for a single resource is a series of joins.

```sql
SELECT
    p.resource_id,
    a.name AS attribute,
    p.source_id,
    sk.key_name AS source_key,
    p.priority,
    v.value_text,
    v.value_num,
    v.value_json
FROM og_field_resource_attribute_priority AS p
JOIN oil_gas_field_source_values AS v
  ON v.source_id = p.source_id
 AND v.attribute_id = p.attribute_id
JOIN og_field_attributes AS a
  ON a.attribute_id = p.attribute_id
JOIN oil_gas_field_sources AS s
  ON s.source_id = p.source_id
JOIN source_key AS sk
  ON sk.source_key_id = s.source_key_id
JOIN user_source_key_permission AS permission
  ON permission.source_key_id = s.source_key_id
 AND permission.user_id = $1
 AND permission.action = 'view'
WHERE p.resource_id = $2
ORDER BY p.priority, p.source_id;
```

| Today                                     | After                                                |
| ----------------------------------------- | ---------------------------------------------------- |
| Tiered `ROW_NUMBER()` over four sort keys | `ORDER BY priority` on one column                    |
| Curated and default rows form two tiers   | Every candidate has an explicit row; no tiers        |
| NULL values skipped by the query          | A priority row exists only where a value exists (FK) |
| Complex CTE chain                         | Joins                                                |

Two consequences to handle in the migration:

- `MembershipModel.source` and the override table's `source` column currently FK to
  `og_field_source_priority.source`. Dropping that table needs a new target for
  that closed set (a `og_field_source_keys` table, or a CHECK).
- `og_field_memberships` has a surrogate `id` primary key and no unique constraint
  on `(resource_id, source_pk)`. Adding one is a prerequisite for the priority
  table to enforce "the source is attached to this resource" by foreign key.
- `is_override` is part of the public per-field source-values response and is
  currently derived from "an override row exists." With every row explicit, it
  needs an explicit `is_curated` flag to survive.

## 4. Proposal, part 2 — a flattened per-profile state table

`og_field_resource_state`, one row per `(resource_id, profile)`:

- one typed column per `OilGasFieldBase` attribute, following `ATTRIBUTE_KINDS`
- `provenance jsonb` — `{attribute_name: source_key}` for the winning source
- primary key `(resource_id, profile)`

**Why four rows per resource is enough.** Every registered user is granted read on
the five public sources (`gem`, `rmi`, `llm`, `alb`, `bc`) by our Auth0 tenant
policy. The only variables are `wm` and `ccr`, so a caller's visibility is two
bits and the profile domain is exactly:

| Profile         | `wm` | `ccr` |
| --------------- | ---- | ----- |
| `public`        | no   | no    |
| `public_wm`     | yes  | no    |
| `public_ccr`    | no   | yes   |
| `public_wm_ccr` | yes  | yes   |

Within one attribute, any candidate ranked below the highest-priority _public_
candidate can never win for anyone, so only candidates ranked above it matter, and
those are `wm` or `ccr` rows. Most attributes therefore produce the same value in
all four rows; only an attribute where a licensed source outranks the best public
source differs. A resource whose `name_local` is ordered `wm, ccr, gem` and whose
other attributes are ordered `gem, wm, ccr` differs across profiles in
`name_local` alone.

Rows exist even when every attribute is null for that profile, which is what
preserves the null-shell behavior of `_resource_universe()`.

## 5. Invariants

The point of §3 and §4 is to push these into the schema. Being explicit about which
ones the database can enforce and which remain obligations on the sync is what
makes the sync mechanism a free choice.

**Enforced declaratively**

| #   | Invariant                                                                    | Mechanism                                             |
| --- | ---------------------------------------------------------------------------- | ----------------------------------------------------- |
| 1   | A priority row references a source attached to that resource                 | composite FK to membership `(resource_id, source_pk)` |
| 2   | A priority row references a populated `(source, attribute)` value            | composite FK to the value table                       |
| 3   | Two sources cannot share a priority position for one `(resource, attribute)` | UNIQUE `(resource_id, attribute_id, priority)`        |
| 4   | A source appears at most once per `(resource, attribute)`                    | primary key                                           |
| 5   | `priority >= 0`                                                              | CHECK                                                 |
| 6   | Attribute references come from the closed attribute set                      | FK to `og_field_attributes`                           |
| 7   | One state row per `(resource, profile)`                                      | primary key                                           |
| 8   | `profile` is one of the four values                                          | CHECK or enum                                         |
| 9   | A state row references an existing resource                                  | FK                                                    |

**Sync obligations** (not expressible as row constraints; a trigger or a
consistency check job, decided with §6)

| #   | Obligation                                                                   |
| --- | ---------------------------------------------------------------------------- |
| A   | Only resources with `repointed_id IS NULL` appear in the state table         |
| B   | All four profile rows exist for every resource in the state table            |
| C   | A provenance entry exists exactly when the matching value column is non-null |
| D   | A provenance source key is visible in that row's profile                     |

Obligation C is expressible as a jsonb CHECK in Postgres but not in SQLite, so
whether to enforce it in the schema depends on the STIT-603 outcome.

## 6. Refresh

Deferred by design. Any implementation must uphold §5 and must be triggered by:
a source value write, a priority change, a membership status change, a resource
repoint (merge), and a bulk ETL load.

The candidate mechanisms are application-transaction maintenance plus a full
rebuild command, database triggers, or a scheduled rebuild. The choice turns
partly on an open question: the ETL apps live in a separate repository and may
write source data without passing through the API's write paths.

## 7. Tradeoffs and risks

- **The four-profile bound rests on the Auth0 policy, not the schema.**
  `permissions.licensed_sources()` derives the set from individual
  `source:read:<key>` claims, so a partial public grant is representable. If one
  were ever issued, that user would read values from a source they are not
  licensed for. Mitigation: map a caller's claims to a profile at request time by
  checking only `wm` and `ccr`, and fail loudly on an unmappable set.
- **`detail` is only half solved.** Its `source_data` payload needs every
  candidate row, not just winners, so the candidate query stays on that path.
- **Write amplification.** One source value write can rewrite up to four state
  rows.
- **Two-table schema changes.** Adding a field to `OilGasFieldBase` becomes a
  migration against both `og_field_attributes` and the state table's columns,
  where today it is a change to `ATTRIBUTE_KINDS` and a CHECK.
- **Priority row volume.** Rows scale as resources × sources × populated
  attributes rather than the current handful. Needs an estimate before approval.
- **`og_field_attributes` is a second source of truth** for the attribute set,
  alongside `OilGasFieldBase`. It needs a startup drift guard like the existing
  `OGFieldName` check.

## 8. Open questions

1. Priority row count at current and projected resource volume.
2. Should `filter-options` read `SELECT DISTINCT` from the state table, or does it
   warrant its own small per-profile distinct-values table?
3. Do the ETL apps write source data directly to the database, bypassing the API?
4. Migration and backfill sequencing: can the state table be built and validated
   against the live query path before any endpoint reads from it?
5. Does anything depend on priority numbers being globally unique per source, as
   `og_field_source_priority.priority` is today?

## Related Documents and Links
