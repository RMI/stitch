import { useEffect, useState } from "react";

function relativeLabel(at) {
  const seconds = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

// Live "Updated N ago" indicator; re-renders on its own so the relative time
// keeps counting up after the last poll.
export default function LastUpdated({ at }) {
  const [, tick] = useState(0);

  useEffect(() => {
    if (!at) return undefined;
    const id = setInterval(() => tick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, [at]);

  if (!at) return null;

  return (
    <span className="text-xs text-ink-muted">Updated {relativeLabel(at)}</span>
  );
}
