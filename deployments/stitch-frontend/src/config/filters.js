import { getCountryName } from "../constants/countries";

// Add entries here to expose new filter dropdowns.
// `formatValue` (optional) maps the stored value to a display label; the raw
// value is still what gets sent to the API as the filter.
// `searchable` (optional) adds a type-to-filter box to the dropdown, for the
// long, open-ended lists; short fixed lists don't need one.
export const FILTER_FIELDS = [
  {
    key: "country",
    label: "Country",
    formatValue: getCountryName,
    searchable: true,
  },
  { key: "region", label: "Region", searchable: true },
  { key: "state_province", label: "State/Province", searchable: true },
  { key: "basin", label: "Basin", searchable: true },
  { key: "field_status", label: "Field status" },
  { key: "primary_hydrocarbon_group", label: "Primary hydrocarbon group" },
];

export const EMPTY_FILTERS = Object.fromEntries(
  FILTER_FIELDS.map((f) => [f.key, []]),
);
