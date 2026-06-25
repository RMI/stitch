import FilterDropdown from "./FilterDropdown";
import { FILTER_FIELDS, EMPTY_FILTERS } from "../config/filters";
import { useResourceFilterOptions } from "../hooks/useResources";

function FilterFieldDropdown({
  endpoint,
  field,
  label,
  formatValue,
  selected,
  onChange,
}) {
  const { data } = useResourceFilterOptions(endpoint, field);
  const options = (data?.values ?? []).map((value) => ({
    value,
    label: formatValue ? formatValue(value) : value,
  }));

  return (
    <FilterDropdown
      label={label}
      options={options}
      selected={selected}
      onChange={onChange}
    />
  );
}

export default function FilterBar({ endpoint, filters, onFiltersChange }) {
  // Flatten active filters into chips: [{ field, label, value, displayValue }, ...]
  // `value` is the stored/API value; `displayValue` is what the user sees.
  const chips = FILTER_FIELDS.flatMap(({ key, label, formatValue }) =>
    (filters[key] ?? []).map((value) => ({
      field: key,
      label,
      value,
      displayValue: formatValue ? formatValue(value) : value,
    })),
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
        {FILTER_FIELDS.map(({ key, label, formatValue }) => (
          <FilterFieldDropdown
            key={key}
            endpoint={endpoint}
            field={key}
            label={label}
            formatValue={formatValue}
            selected={filters[key] ?? []}
            onChange={(values) => handleDropdownChange(key, values)}
          />
        ))}
      </div>

      {/* Chips + clear button — only rendered when at least one filter is active */}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {chips.map(({ field, label, value, displayValue }) => (
            <span
              key={`${field}:${value}`}
              className="flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1.5 text-xs text-ink"
            >
              <span>
                <span className="font-medium">{label}:</span> {displayValue}
              </span>
              <button
                type="button"
                onClick={() => removeChip(field, value)}
                aria-label={`Remove ${label}: ${displayValue}`}
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
