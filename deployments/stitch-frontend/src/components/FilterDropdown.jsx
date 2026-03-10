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
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm transition-colors text-gray-dark ${
          isActive
            ? " bg-gray-light border-gray-button-outline"
            : " bg-none border-transparent  hover:border-gray-button-outline hover:bg-gray-light"
        }`}
      >
        {label}
        {isActive && (
          <span className="rounded-full bg-gray-dark px-1.5 min-w-5 py-0.5 text-xs font-medium text-gray-light">
            {selectedCount}
          </span>
        )}
        <span className={`text-xs scale-y-60 text-gray-dark`}>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="absolute z-10 mt-1 min-w-48 rounded border border-gray-200 bg-white shadow-lg">
          {options.length === 0 ? (
            <p className="px-3 py-2 text-sm text-gray-400">No options</p>
          ) : (
            <ul className="max-h-60 overflow-y-auto py-1">
              {options.map(({ value, count }) => (
                <li key={value}>
                  <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-gray-50">
                    <input
                      type="checkbox"
                      checked={selected.includes(value)}
                      onChange={() => toggleValue(value)}
                      className="accent-blue-500"
                    />
                    <span className="flex-1 text-sm text-gray-700">
                      {value}
                    </span>
                    <span className="text-xs text-gray-400">{count}</span>
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
