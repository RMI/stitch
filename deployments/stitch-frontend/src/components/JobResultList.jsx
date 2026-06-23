import { useState } from "react";

const STATE_STYLES = {
  running: "border-warning/30 bg-warning-soft text-warning",
  succeeded: "border-success/25 bg-success-soft text-success-strong",
  failed: "border-danger/25 bg-danger-soft text-danger",
};

const DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function StateBadge({ state }) {
  if (!state) return null;
  const classes = STATE_STYLES[state] ?? "border-line bg-surface text-ink";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${classes}`}
    >
      {state}
    </span>
  );
}

function formatStartedAt(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE_FORMATTER.format(date);
}

// Collapsible list of job records, newest first, with the most recent expanded
// by default. Each service supplies `renderResult(record)` for the body.
export default function JobResultList({ records, renderResult }) {
  // Per-item user overrides; absent → default (newest open, others collapsed).
  // Derived rather than effect-driven so the newest run stays expanded as new
  // runs arrive, without a set-state-in-effect.
  const [overrides, setOverrides] = useState({});
  const newestId = records[0]?.job_id;

  if (!records.length) return null;

  const isOpen = (id) => overrides[id] ?? id === newestId;

  function toggle(id) {
    setOverrides((prev) => ({ ...prev, [id]: !isOpen(id) }));
  }

  return (
    <ol className="space-y-2">
      {records.map((record) => {
        const open = isOpen(record.job_id);
        return (
          <li
            key={record.job_id}
            className="overflow-hidden rounded-md border border-line bg-surface"
          >
            <button
              type="button"
              aria-expanded={open}
              onClick={() => toggle(record.job_id)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm font-medium text-ink"
            >
              <span className="flex items-center gap-2">
                <span aria-hidden="true" className="text-ink-muted">
                  {open ? "−" : "+"}
                </span>
                <span>{formatStartedAt(record.started_at)}</span>
              </span>
              <StateBadge state={record.state} />
            </button>
            {open && (
              <div className="border-t border-line p-3">
                {renderResult(record)}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
