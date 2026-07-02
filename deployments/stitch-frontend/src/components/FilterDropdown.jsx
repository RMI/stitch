import { useState, useRef, useEffect } from "react";

export default function FilterDropdown({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

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

  const selectedCount = selected.length;
  const isActive = selectedCount > 0;

  return (
    <div ref={ref} className="relative">
      <button
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
        <div className="absolute z-10 mt-1 min-w-52 rounded-md border border-line bg-panel shadow-sm">
          {options.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-muted">No options</p>
          ) : (
            <ul className="max-h-60 overflow-y-auto py-1" role="listbox">
              {options.map(({ value, label, count }) => (
                <li key={value}>
                  <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-surface">
                    <input
                      type="checkbox"
                      checked={selected.includes(value)}
                      onChange={() => toggleValue(value)}
                      className="accent-primary"
                    />
                    <span className="flex-1 text-sm text-ink">
                      {label ?? value}
                    </span>
                    {count != null && (
                      <span className="text-xs text-ink-muted">{count}</span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
