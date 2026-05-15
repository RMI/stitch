import {
  SOURCES,
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

function formatFieldCount(count) {
  return `${count} field${count === 1 ? "" : "s"}`;
}

function buildSourceEntries(provenance) {
  const countsBySource = Object.fromEntries(
    SOURCES.map((source) => [source, 0]),
  );
  let unknownCount = 0;

  for (const value of Object.values(provenance ?? {})) {
    if (!value) continue;
    if (SOURCES.includes(value)) {
      countsBySource[value] += 1;
    } else {
      unknownCount += 1;
    }
  }

  const entries = SOURCES.map((source) => ({
    source,
    count: countsBySource[source],
    label: SOURCE_LABELS[source],
    color: SOURCE_COLORS[source],
  })).filter(({ count }) => count > 0);

  if (unknownCount > 0) {
    entries.push({
      source: "unknown",
      count: unknownCount,
      label: UNKNOWN_SOURCE_LABEL,
      color: DEFAULT_FIELD_COLOR,
    });
  }

  return entries;
}

export default function SourceMixBar({ provenance, showLabels = false }) {
  const activeSources = buildSourceEntries(provenance);
  const total = activeSources.reduce((sum, { count }) => sum + count, 0);

  if (total === 0) {
    return (
      <div
        className="w-full"
        role="group"
        aria-label="Data source mix: no source data available"
      >
        <div
          className="h-3 w-full rounded-sm bg-surface-tint"
          title="No source data"
          aria-hidden="true"
        />
        <p className="mt-1 text-xs leading-4 text-ink-muted">No source data</p>
      </div>
    );
  }

  const entries = activeSources.map((entry) => ({
    ...entry,
    pct: (entry.count / total) * 100,
  }));
  const sourceSummary = entries
    .map(
      ({ label, count, pct }) =>
        `${label}: ${formatFieldCount(count)} (${Math.round(pct)}%)`,
    )
    .join("; ");

  return (
    <div
      className="w-full min-w-0"
      role="group"
      aria-label={`Data source mix: ${sourceSummary}`}
    >
      {showLabels && (
        <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
          {entries.map(({ source, label, count, pct, color }) => (
            <div
              key={source}
              className="flex min-w-0 items-center gap-1.5 text-sm font-medium text-ink"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-ink/10"
                style={{ backgroundColor: color }}
                aria-hidden="true"
              />
              <span className="break-words">
                {label}: {formatFieldCount(count)} ({Math.round(pct)}%)
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex h-4 w-full overflow-hidden rounded-sm bg-surface-tint ring-1 ring-line">
        {entries.map(({ source, label, count, pct, color }) => (
          <div
            key={source}
            style={{ width: `${pct}%`, backgroundColor: color }}
            title={`${label}: ${formatFieldCount(count)} (${Math.round(pct)}%)`}
            aria-hidden="true"
          />
        ))}
      </div>
      {!showLabels && (
        <p className="mt-1 truncate text-xs leading-4 text-ink-muted">
          {sourceSummary}
        </p>
      )}
    </div>
  );
}
