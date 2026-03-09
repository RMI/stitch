import { SOURCE_COLORS, DEFAULT_FIELD_COLOR } from "../constants/sourceMeta";

// Used to display a single field value in a card, as seen in the ResourceDetailPage.
// Pass `source` (one of "gem" | "wm" | "rmi" | "llm") to tint the left border by data source.
export function FieldCard({ label, value, source }) {
  const display =
    value === null || value === undefined || value === "" ? null : String(value);
  const borderColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;

  return (
    <div>
      <p className="text-base text-gray-dark mb-1 text-left font-medium">{label}</p>
      <div
        className="bg-gray-light border-l-4 px-3 py-2 text-base text-gray-dark min-h-[2.25rem] rounded-sm"
        style={{ borderLeftColor: borderColor }}
      >
        {display ?? <span className="text-gray-dark">—</span>}
      </div>
    </div>
  );
}

export function FieldGrid({ children }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-5">
      {children}
    </div>
  );
}
