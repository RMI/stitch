export function isEmptyValue(value) {
  return value === null || value === undefined || value === "";
}

// Two values are considered equal if they are exactly equal, or if both are
// strings that are equal ignoring case.
function valuesMatch(a, b) {
  if (typeof a === "string" && typeof b === "string") {
    return a.toLowerCase() === b.toLowerCase();
  }
  return a === b;
}

// Row status across all source values: "match" when every source has the same
// populated value (exact ===, or case-insensitive for strings), "differs" when
// populated values disagree or only some sources have a value, "empty" when no
// source has a value.
export function getRowStatus(values) {
  const populated = values.filter((value) => !isEmptyValue(value));
  if (populated.length === 0) return "empty";
  if (populated.length < values.length) return "differs";
  return populated.every((value) => valuesMatch(value, populated[0]))
    ? "match"
    : "differs";
}
