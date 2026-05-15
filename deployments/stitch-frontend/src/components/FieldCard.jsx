import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

// Used to display a single field value in a card, as seen in the ResourceDetailPage.
// Pass `source` (one of "gem" | "wm" | "rmi" | "llm") to tint the left border by data source.
export function FieldCard({ label, value, source }) {
  const display =
    value === null || value === undefined || value === ""
      ? null
      : String(value);
  const borderColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;
  const hasSource = source !== null && source !== undefined && source !== "";
  const sourceLabel = hasSource
    ? (SOURCE_LABELS[source] ?? UNKNOWN_SOURCE_LABEL)
    : null;

  return (
    <div className="min-w-0">
      <p className="mb-1 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      <div
        className="min-h-[2.5rem] rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink"
        style={{ borderLeftColor: borderColor }}
        title={sourceLabel ? `Source: ${sourceLabel}` : undefined}
      >
        <div className="break-words">
          {display ?? <span className="text-ink-muted">—</span>}
        </div>
        {sourceLabel && (
          <div className="mt-1 flex items-center gap-1.5 text-xs font-medium leading-4 text-ink-muted">
            <span
              className="h-2 w-2 shrink-0 rounded-sm ring-1 ring-ink/10"
              style={{ backgroundColor: borderColor }}
              aria-hidden="true"
            />
            Source: {sourceLabel}
          </div>
        )}
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
