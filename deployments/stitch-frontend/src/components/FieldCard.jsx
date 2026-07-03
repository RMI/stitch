import { useId, useState } from "react";
import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

function SourceValueRow({ source, value, id, isWinner }) {
  const barColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;
  const sourceLabel = SOURCE_LABELS[source] ?? UNKNOWN_SOURCE_LABEL;
  const meta =
    id !== null && id !== undefined ? `${sourceLabel} · #${id}` : sourceLabel;

  return (
    <div
      className={`rounded-md border border-line border-l-4 px-2.5 py-1.5 ${
        isWinner ? "bg-surface" : "bg-panel"
      }`}
      style={{ borderLeftColor: barColor }}
    >
      <div className="break-words text-sm text-ink">"{String(value)}"</div>
      <div className="mt-0.5 text-xs text-ink-muted">{meta}</div>
    </div>
  );
}

function FieldSourcesPanel({ id, sources }) {
  return (
    <div
      id={id}
      className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3"
    >
      {/* Reserved header — future controls will live alongside this label. */}
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        All sources
      </p>
      <div className="space-y-1.5">
        {sources.map((row) => (
          <SourceValueRow
            key={`${row.source}-${row.id ?? row.value}`}
            source={row.source}
            value={row.value}
            id={row.id}
            isWinner={row.isWinner}
          />
        ))}
      </div>
    </div>
  );
}

// Used to display a single field value in a card, as seen in the ResourceDetailPage.
// Pass `source` (one of "gem" | "wm" | "rmi" | "llm") to tint the left border by data source.
// Pass `sources` (from getFieldSources) to make the value clickable, revealing an
// inline "All sources" panel with every competing source value.
export function FieldCard({ label, value, source, sources }) {
  const [isOpen, setIsOpen] = useState(false);
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
  const isInteractive = Array.isArray(sources) && sources.length > 0;

  const boxContent = (
    <>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1 break-words">
          {display ?? <span className="text-ink-muted">—</span>}
        </div>
        {isInteractive && (
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
    "min-h-[2.5rem] w-full rounded-md border border-line bg-panel px-3 py-2 text-left text-sm text-ink";

  return (
    <div className="min-w-0">
      <p className="mb-1 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      {isInteractive ? (
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={() => setIsOpen((current) => !current)}
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
      {isInteractive && isOpen && (
        <FieldSourcesPanel id={panelId} sources={sources} />
      )}
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
