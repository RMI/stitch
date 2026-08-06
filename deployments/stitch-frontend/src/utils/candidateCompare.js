// Helpers for the `compare` object on the merge-candidate detail response:
// one entry per field with a backend-computed status and per-source values
// sorted winner-first. The backend omits null values (a resource with no
// value has no entry) but includes "" as a real value.

export function compareEntry(compare, field) {
  return compare?.find((entry) => entry.field === field) ?? null;
}

export function valueEntryForResource(entry, resourceId) {
  return entry?.values.find((v) => v.resource_id === resourceId) ?? null;
}

// The winning name across all sources: the first entry of the `name` field's
// values. An empty-string winner is a real value for comparison purposes but
// useless as a heading, so it falls back to null.
export function pickCompareName(compare) {
  const winner = compareEntry(compare, "name")?.values[0]?.value;
  return winner == null || winner === "" ? null : winner;
}
