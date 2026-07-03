import { SOURCES } from "../constants/sourceMeta";

const RESOURCE_LIST_DATA_EXCLUDED_FIELDS = new Set([
  "id",
  "source_data",
  "repointed_to",
  "constituents",
  "provenance",
]);

export function getResourceField(resource, key) {
  return resource?.data?.[key] ?? resource?.[key] ?? null;
}

export function isPrimitive(value) {
  return (
    value == null || ["string", "number", "boolean"].includes(typeof value)
  );
}

export function deriveProvenance(resource) {
  if (resource?.provenance) return resource.provenance;
  if (!resource?.source_data) return {};

  const data = resource.data ?? resource;
  const provenance = {};

  for (const [field, value] of Object.entries(data)) {
    if (!isPrimitive(value) || field === "id") continue;

    // SOURCES order intentionally decides the winner for duplicate field values.
    for (const source of SOURCES) {
      const records = resource.source_data[source] ?? [];
      if (records.some((record) => record?.[field] === value)) {
        provenance[field] = source;
        break;
      }
    }
  }

  return provenance;
}

/**
 * All source values competing for a single field, best-first.
 *
 * Reads the per-field values already present on the detail view's `source_data`
 * (no extra request). The winner is the record whose source matches
 * `provenance[fieldKey]` and whose value equals the coalesced `data[fieldKey]`.
 * Losers follow, ordered by the effective per-resource `source_priority`
 * (lower = higher priority), tie-broken by source row id.
 *
 * Returns `[]` when nothing has a value for the field (empty-handling), so the
 * caller can leave the field non-interactive.
 */
export function getFieldSources(detailView, fieldKey) {
  const records = detailView?.source_data;
  if (!Array.isArray(records)) return [];

  const winnerSource = detailView.provenance?.[fieldKey] ?? null;
  const winnerValue = detailView.data?.[fieldKey];
  const priority = detailView.source_priority ?? {};
  // Fallback rank keeps ordering stable when a source is absent from the map.
  const rankOf = (source) =>
    Object.prototype.hasOwnProperty.call(priority, source)
      ? priority[source]
      : Number.MAX_SAFE_INTEGER;

  const rows = [];
  for (const record of records) {
    const value = record?.[fieldKey];
    if (value === null || value === undefined || value === "") continue;
    rows.push({
      id: record.id ?? null,
      source: record.source,
      value,
      isWinner: record.source === winnerSource && value === winnerValue,
    });
  }

  rows.sort((a, b) => {
    if (a.isWinner !== b.isWinner) return a.isWinner ? -1 : 1;
    const rankDiff = rankOf(a.source) - rankOf(b.source);
    if (rankDiff !== 0) return rankDiff;
    return (a.id ?? 0) - (b.id ?? 0);
  });

  return rows;
}

export function normalizeResourceListItem(resource) {
  if (!resource || resource.data) {
    return resource;
  }

  const data = Object.fromEntries(
    Object.entries(resource).filter(
      ([key]) => !RESOURCE_LIST_DATA_EXCLUDED_FIELDS.has(key),
    ),
  );

  return {
    ...resource,
    id: resource.id,
    data,
    provenance: deriveProvenance(resource),
  };
}
