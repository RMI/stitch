/**
 * Column definitions for the resources list table.
 *
 * These live outside the table component because two very different consumers
 * need them: the table renders them, and the URL schema (config/listParams.js)
 * validates `sort_by` against them. A component module cannot export both a
 * component and shared constants without breaking Fast Refresh, so the shared
 * data lives here instead.
 */
import { getCountryName } from "../constants/countries";

// sortType: "string" | "number", omit sortable (or set false) to disable sorting for a column.
// format: optional (value) => displayValue applied to the cell's raw value.
export const COLUMNS = [
  {
    label: "Name",
    key: "name",
    className: "font-semibold text-ink",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Country",
    key: "country",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
    format: getCountryName,
  },
  {
    label: "State/Province",
    key: "state_province",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Region",
    key: "region",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Basin",
    key: "basin",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Field status",
    key: "field_status",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Primary hydrocarbon group",
    key: "primary_hydrocarbon_group",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
];

// The canonical list of columns the API can sort by, used by the URL schema
// (config/listParams.js) to validate sort_by against one source of truth.
export const SORTABLE_COLUMN_KEYS = COLUMNS.filter((col) => col.sortable).map(
  (col) => col.key,
);
