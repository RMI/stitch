import { useState, useRef, useEffect } from "react";

// Lowercases and strips accents, so "cote" matches "Côte d'Ivoire". NFD splits
// accented letters into a base letter plus combining marks (\p{M}), which are
// then dropped. Letters with no decomposition, like "ø", are left as they are.
// Curly apostrophes (as in Intl.DisplayNames' "Côte d’Ivoire") become straight
// ones, so what a keyboard types still matches.
function normalizeForSearch(text) {
  return String(text)
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[‘’ʼ]/g, "'")
    .toLowerCase();
}

// The open dropdown's contents. It mounts when the dropdown opens and unmounts
// when it closes, so the search text always starts empty.
function FilterDropdownPanel({
  label,
  options,
  selected,
  onToggle,
  searchable,
  onClose,
}) {
  const [query, setQuery] = useState("");

  const normalizedQuery = normalizeForSearch(query.trim());
  const visibleOptions = normalizedQuery
    ? options.filter((option) =>
        normalizeForSearch(option.label ?? option.value).includes(
          normalizedQuery,
        ),
      )
    : options;

  return (
    <div className="absolute z-10 mt-1 min-w-52 rounded-md border border-line bg-panel shadow-sm">
      {options.length === 0 ? (
        <p className="px-3 py-2 text-sm text-ink-muted">No options</p>
      ) : (
        <>
          {searchable && (
            <div className="border-b border-line p-2">
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    onClose();
                  }
                }}
                placeholder={`Search ${label}`}
                aria-label={`Search ${label}`}
                // Opening the dropdown is the intent to pick; let typing
                // start immediately.
                autoFocus
                className="min-h-9 w-full rounded-md border border-line bg-panel px-3 py-1.5 text-sm text-ink transition-colors hover:border-line-strong focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
          )}
          {visibleOptions.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-muted">No matches</p>
          ) : (
            <ul className="max-h-60 overflow-y-auto py-1" role="listbox">
              {visibleOptions.map(({ value, label: optionLabel, count }) => (
                <li key={value}>
                  <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-surface">
                    <input
                      type="checkbox"
                      checked={selected.includes(value)}
                      onChange={() => onToggle(value)}
                      className="accent-primary"
                    />
                    <span className="flex-1 text-sm text-ink">
                      {optionLabel ?? value}
                    </span>
                    {count != null && (
                      <span className="text-xs text-ink-muted">{count}</span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

export default function FilterDropdown({
  label,
  options,
  selected,
  onChange,
  searchable = false,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const buttonRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function toggleValue(value) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  // Escape from the search box closes the dropdown and puts focus back on its
  // button, so keyboard users are not left on an element that just vanished.
  function closeFromSearch() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  const selectedCount = selected.length;
  const isActive = selectedCount > 0;

  return (
    <div ref={ref} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex min-h-9 items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium text-ink transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 ${
          isActive
            ? "border-primary/30 bg-primary-soft text-primary"
            : "border-line bg-panel hover:border-line-strong hover:bg-surface"
        }`}
      >
        {label}
        {isActive && (
          <span className="min-w-5 rounded-full bg-primary px-1.5 py-0.5 text-xs font-semibold text-white">
            {selectedCount}
          </span>
        )}
        <span className="text-xs text-current" aria-hidden="true">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <FilterDropdownPanel
          label={label}
          options={options}
          selected={selected}
          onToggle={toggleValue}
          searchable={searchable}
          onClose={closeFromSearch}
        />
      )}
    </div>
  );
}
