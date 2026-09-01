import { useId } from "react";
import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

// Used to display a single field value in a card, as seen in the ResourceDetailPage.
// Pass `source` (one of "gem" | "wm" | "ccr" | "bc" | "alb" | "rmi" | "llm") to tint the left border by data source.
// Pass `expandable` + `isOpen` + `onToggle` to make the value a toggle button; `children`
// (e.g. an "All sources" panel) render below the box while open. The card is presentational:
// the parent owns open state and any data fetching.
export function FieldCard({
  label,
  value,
  source,
  expandable = false,
  isOpen = false,
  onToggle,
  children,
}) {
  const panelId = useId();
  const display =
    value === null || value === undefined || value === ""
      ? null
      : String(value);
  const borderColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;
  const hasSource = source !== null && source !== undefined && source !== "";
  const sourceLabel = hasSource
    ? (SOURCE_LABELS[source] ?? UNKNOWN_SOURCE_LABEL)
    : null;

  const boxContent = (
    <>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1 break-words">
          {display ?? <span className="text-ink-muted">—</span>}
        </div>
        {expandable && (
          <span aria-hidden="true" className="shrink-0 text-xs text-ink-muted">
            {isOpen ? "▾" : "▸"}
          </span>
        )}
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
    </>
  );

  const boxClasses =
    "min-h-[2.5rem] w-full rounded-md border border-line border-l-4 bg-panel px-3 py-2 text-left text-sm text-ink";

  return (
    <div className="min-w-0">
      <p className="mb-1 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      {expandable ? (
        <button
          type="button"
          aria-expanded={isOpen}
          // Only reference the panel while it is mounted (rendered on open).
          aria-controls={isOpen ? panelId : undefined}
          onClick={onToggle}
          className={`${boxClasses} transition-colors hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-1`}
          style={{ borderLeftColor: borderColor }}
        >
          {boxContent}
        </button>
      ) : (
        <div
          className={boxClasses}
          style={{ borderLeftColor: borderColor }}
          title={sourceLabel ? `Source: ${sourceLabel}` : undefined}
        >
          {boxContent}
        </div>
      )}
      {expandable && isOpen && <div id={panelId}>{children}</div>}
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
