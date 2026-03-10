const SOURCES = ["gem", "wm", "rmi", "llm"];

const SOURCE_COLORS = {
  gem: "#4AE3D9", // teal
  wm: "#3B44EC", // purple
  rmi: "#F4A70B", // orange
  llm: "#57A0FF", // light blue
};

export default function SourceMixBar({ sourceData }) {
  const counts = SOURCES.map((s) => sourceData?.[s]?.length ?? 0);
  const total = counts.reduce((a, b) => a + b, 0);

  if (total === 0) {
    return (
      <div className="h-3 w-full rounded bg-gray-200" title="No source data" />
    );
  }

  return (
    <div className="flex h-5 w-full overflow-hidden">
      {SOURCES.map((s, i) => {
        const pct = (counts[i] / total) * 100;
        if (pct === 0) return null;
        return (
          <div
            key={s}
            style={{ width: `${pct}%`, backgroundColor: SOURCE_COLORS[s] }}
            title={`${s.toUpperCase()}: ${counts[i]} record${counts[i] !== 1 ? "s" : ""} (${Math.round(pct)}%)`}
          />
        );
      })}
    </div>
  );
}
