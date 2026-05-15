import { useMemo } from "react";
import FilterDropdown from "./FilterDropdown";
import { FILTER_FIELDS, EMPTY_FILTERS } from "../config/filters";
import { getResourceField } from "../utils/resourceDisplay";

// Compute sorted option list with static counts from the full dataset.
function buildOptions(resources, field) {
  const counts = {};
  for (const r of resources) {
    const val = getResourceField(r, field);
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
    <div className="space-y-2" data-testid="filter-bar">
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
              className="flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1.5 text-xs text-ink"
            >
              <span>
                <span className="font-medium">{label}:</span> {value}
              </span>
              <button
                type="button"
                onClick={() => removeChip(field, value)}
                aria-label={`Remove ${label}: ${value}`}
                className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-ink text-panel hover:bg-ink/80 hover:cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                <span className="leading-none -translate-y-px font-semibold">
                  ×
                </span>
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={() => onFiltersChange(EMPTY_FILTERS)}
            className="rounded-md border border-line bg-panel px-2 py-1.5 text-xs font-medium text-ink hover:bg-surface hover:cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
