import Button from "./Button";

// Smart trigger for a job: its label reflects whether a result already exists
// and whether a forced re-run is requested, and it shows a spinner while the
// job is running/polling.
//
// labels: { running, show, create, recreate }
//   - running  → shown with a spinner while a run is in flight
//   - show     → a prior result exists and hasn't been revealed yet
//   - recreate → force is toggled on (re-run)
//   - create   → no prior result; first run
export default function JobTriggerButton({
  running,
  force,
  hasExisting,
  revealed,
  labels,
  onClick,
  disabled = false,
  variant = "secondary",
}) {
  let label;
  if (running) label = labels.running;
  else if (force) label = labels.recreate;
  else if (hasExisting && !revealed) label = labels.show;
  else label = labels.create;

  return (
    <Button onClick={onClick} disabled={disabled || running} variant={variant}>
      {running ? (
        <span className="inline-flex items-center gap-2">
          <span
            aria-hidden="true"
            className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          {label}
        </span>
      ) : (
        label
      )}
    </Button>
  );
}
