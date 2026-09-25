# Stitch Architecture

## Project Structure

`stitch` is organized as a monorepo. This allows for clean separation of core components & functionality, deployed applications and services, and development/deployment support features.

**`packages/`**

- Contains the various core components and domain logic in separate, versioned packages

**`deployments/`**

- Houses our deployable applications and any public, published packages

**`dev/`**

- Contains miscellaneous development support tooling and scripts

## Read model: coalesced oil & gas fields

A "resource" (an oil & gas field) draws its attribute values from multiple source
records attached via memberships. For each `(resource, field)` the value shown is
**coalesced**: the highest-priority source wins, where priority is a per-field
curator override tier first, then the global source order
(`stitch.ogsi.model.SOURCE_PRIORITY`). This ranking is defined once in SQL
(`queries._ranked`) and is the single source of truth for "who beats whom".

Recomputing that ranking on every request was the read bottleneck, so the winners
are precomputed into the **`og_field_resource_state`** table: the full ranked
candidate list per `(resource, field)` for every non-repointed resource. The hot
read paths — `list`, `filter-options`, and `detail` — read coalesced winners from
this table and never rebuild the ranking. `detail` additionally fetches the raw
per-source records (`source_data`) with a separate, ranking-free query.

Key properties:

- **Derived, not authoritative** — every row is rebuildable from memberships +
  source values + priorities (`resource_state.rebuild_all_resource_state`).
- **Maintained by the write paths** — attaching a source, reprioritizing a field,
  and merging each refresh the affected resources in the same transaction
  (`resource_state.refresh_resource_state`), so reads are never stale.
- **Permissions stay in the application** — the table stores the full candidate
  list with no licensing baked in; each read filters to the caller's licensed
  sources and takes the top surviving rank, exactly as the live query did.

The source-list and per-field-sources (curator) endpoints still rank on the fly,
as they need every source record rather than the coalesced winner.
