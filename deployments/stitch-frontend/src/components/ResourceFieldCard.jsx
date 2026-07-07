import { useState } from "react";
import { FieldCard } from "./FieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
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
  // Quote strings to set text values apart; render numbers/booleans bare.
  const display = typeof value === "string" ? `"${value}"` : String(value);

  return (
    <div
      className={`rounded-md border border-line border-l-4 px-2.5 py-1.5 ${
        isWinner ? "bg-surface" : "bg-panel"
      }`}
      style={{ borderLeftColor: barColor }}
    >
      <div className="break-words text-sm text-ink">{display}</div>
      <div className="mt-0.5 text-xs text-ink-muted">{meta}</div>
    </div>
  );
}

function FieldSourcesPanel({ isLoading, isError, sources }) {
  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3">
      {/* Reserved header — future controls will live alongside this label. */}
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        All sources
      </p>
      {isLoading && <p className="text-sm text-ink-muted">Loading sources…</p>}
      {isError && (
        <p className="text-sm text-danger">Failed to load source values.</p>
      )}
      {!isLoading && !isError && sources.length === 0 && (
        <p className="text-sm text-ink-muted">
          No source values for this field.
        </p>
      )}
      {!isLoading && !isError && sources.length > 0 && (
        <div className="space-y-1.5">
          {/* The endpoint returns best-priority first, so index 0 is the winner. */}
          {sources.map((row, idx) => (
            <SourceValueRow
              key={`${row.source}-${row.id}`}
              source={row.source}
              value={row.value}
              id={row.id}
              isWinner={idx === 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// A FieldCard for the resource detail page: clicking a populated value lazily
// fetches every source's value for that field and shows them in priority order.
export default function ResourceFieldCard({
  endpoint,
  resourceId,
  fieldKey,
  label,
  value,
  source,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const expandable = value !== null && value !== undefined && value !== "";
  const { data, isLoading, isError } = useFieldSourceValues(
    endpoint,
    resourceId,
    fieldKey,
    isOpen && expandable,
  );

  return (
    <FieldCard
      label={label}
      value={value}
      source={source}
      expandable={expandable}
      isOpen={isOpen}
      onToggle={() => setIsOpen((current) => !current)}
    >
      <FieldSourcesPanel
        isLoading={isLoading}
        isError={isError}
        sources={data ?? []}
      />
    </FieldCard>
  );
}
