// Add entries here to expose new filter dropdowns.
export const FILTER_FIELDS = [
  { key: "country", label: "Country" },
  { key: "region", label: "Region" },
  { key: "state_province", label: "State/Province" },
  { key: "basin", label: "Basin" },
  { key: "field_status", label: "Field status" },
  { key: "primary_hydrocarbon_group", label: "Primary hydrocarbon group" },
];

export const EMPTY_FILTERS = Object.fromEntries(
  FILTER_FIELDS.map((f) => [f.key, []]),
);
