const STATE_STYLES = {
  running: "border-warning/30 bg-warning-soft text-warning",
  succeeded: "border-success/25 bg-success-soft text-success-strong",
  failed: "border-danger/25 bg-danger-soft text-danger",
};

// Job-state pill used by the ETL batch-workflow page.
export default function StateBadge({ state }) {
  if (!state) return null;

  const classes = STATE_STYLES[state] ?? "border-line bg-surface text-ink";

  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${classes}`}
    >
      {state}
    </span>
  );
}
