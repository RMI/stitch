import { useMemo } from "react";
import FilterDropdown from "./FilterDropdown";
import { FILTER_FIELDS, EMPTY_FILTERS } from "../config/filters";

// Compute sorted option list with static counts from the full dataset.
function buildOptions(resources, field) {
  const counts = {};
  for (const r of resources) {
    const val = r[field];
    if (val != null) counts[val] = (counts[val] ?? 0) + 1;
  }
  return Object.entries(counts)
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => a.value.localeCompare(b.value));
}

export default function FilterBar({ resources, filters, onFiltersChange }) {
  // Memoize per-field options so O(n) passes only re-run when `resources` changes,
  // not on every filter interaction.
  const optionsByField = useMemo(
    () =>
      Object.fromEntries(
        FILTER_FIELDS.map(({ key }) => [key, buildOptions(resources, key)]),
      ),
    [resources],
  );
  // Flatten active filters into chips: [{ field, label, value }, ...]
  const chips = FILTER_FIELDS.flatMap(({ key, label }) =>
    (filters[key] ?? []).map((value) => ({ field: key, label, value })),
  );

  function handleDropdownChange(field, values) {
    onFiltersChange({ ...filters, [field]: values });
  }

  function removeChip(field, value) {
    onFiltersChange({
      ...filters,
      [field]: filters[field].filter((v) => v !== value),
    });
  }

  return (
    <div className="space-y-2">
      {/* Dropdowns row */}
      <div className="flex flex-wrap gap-2">
        {FILTER_FIELDS.map(({ key, label }) => (
          <FilterDropdown
            key={key}
            label={label}
            options={optionsByField[key]}
            selected={filters[key] ?? []}
            onChange={(values) => handleDropdownChange(key, values)}
          />
        ))}
      </div>

      {/* Chips + clear button — only rendered when at least one filter is active */}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {chips.map(({ field, label, value }) => (
            <span
              key={`${field}:${value}`}
              className="flex items-center gap-1 rounded-full bg-gray-light px-2 py-1.5 text-xs text-gray-dark border-gray-button-outline border"
            >
              <span>
                <span className="font-medium">{label}:</span> {value}
              </span>
              <button
                onClick={() => removeChip(field, value)}
                aria-label={`Remove ${label}: ${value}`}
                className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-gray-dark text-gray-light hover:bg-gray-dark/80 hover:cursor-pointer"
              >
                <span className="leading-none -translate-y-px font-bold">
                  ×
                </span>
              </button>
            </span>
          ))}
          <button
            onClick={() => onFiltersChange(EMPTY_FILTERS)}
            className="text-xs px-2 py-1.5 rounded-md bg-gray-light text-gray-dark border-gray-button-outline border hover:bg-gray-medium hover:cursor-pointer"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
