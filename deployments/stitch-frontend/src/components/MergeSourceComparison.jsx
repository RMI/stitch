function isEmpty(value) {
  return value === null || value === undefined || value === "";
}

// Row status across all source values: "match" when every source has the same
// populated value (exact ===), "differs" when populated values disagree or
// only some sources have a value, "empty" when no source has a value.
export function getRowStatus(values) {
  const populated = values.filter((value) => !isEmpty(value));
  if (populated.length === 0) return "empty";
  if (populated.length < values.length) return "differs";
  return populated.every((value) => value === populated[0])
    ? "match"
    : "differs";
}
