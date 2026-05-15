// Add entries here to expose new filter dropdowns.
export const FILTER_FIELDS = [
  { key: "region", label: "Region" },
  { key: "state_province", label: "State/Province" },
  { key: "basin", label: "Basin" },
  { key: "field_status", label: "Field status" },
];

export const EMPTY_FILTERS = Object.fromEntries(
  FILTER_FIELDS.map((f) => [f.key, []]),
);
