import { SOURCES } from "../constants/sourceMeta";

export function getResourceField(resource, key) {
  return resource?.data?.[key] ?? resource?.[key] ?? null;
}

function isPrimitive(value) {
  return (
    value == null || ["string", "number", "boolean"].includes(typeof value)
  );
}

function deriveProvenance(resource) {
  if (resource?.provenance) return resource.provenance;
  if (!resource?.source_data) return {};

  const data = resource.data ?? resource;
  const provenance = {};

  for (const [field, value] of Object.entries(data)) {
    if (!isPrimitive(value) || field === "id") continue;

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

  const data = { ...resource };
  delete data.id;
  delete data.source_data;
  delete data.repointed_to;
  delete data.constituents;
  delete data.provenance;

  return {
    ...resource,
    id: resource.id,
    data,
    provenance: deriveProvenance(resource),
  };
}
