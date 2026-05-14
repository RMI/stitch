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
