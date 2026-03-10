import { SOURCES, SOURCE_COLORS, SOURCE_LABELS } from "../constants/sourceMeta";

export default function SourceMixBar({ sourceData, showLabels = false }) {
  const counts = SOURCES.map((s) => sourceData?.[s]?.length ?? 0);
  const total = counts.reduce((a, b) => a + b, 0);

  if (total === 0) {
    return (
      <div className="h-3 w-full rounded bg-gray-200" title="No source data" />
    );
  }

  const activeSources = SOURCES.map((s, i) => ({
    s,
    count: counts[i],
    pct: (counts[i] / total) * 100,
  })).filter(({ pct }) => pct > 0);

  return (
    <div className="w-full">
      {showLabels && (
        <div className="flex w-full mb-1">
          {activeSources.map(({ s, pct }) => (
            <div
              key={s}
              style={{ width: `${pct}%` }}
              className="text-base font-medium text-gray-dark truncate pr-1"
            >
              {SOURCE_LABELS[s]}
            </div>
          ))}
        </div>
      )}
      <div className="flex h-5 w-full overflow-hidden">
        {activeSources.map(({ s, count, pct }) => (
          <div
            key={s}
            style={{ width: `${pct}%`, backgroundColor: SOURCE_COLORS[s] }}
            title={`${SOURCE_LABELS[s]}: ${count} record${count !== 1 ? "s" : ""} (${Math.round(pct)}%)`}
          />
        ))}
      </div>
    </div>
  );
}
