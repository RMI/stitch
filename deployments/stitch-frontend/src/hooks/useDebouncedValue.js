import { useEffect, useState } from "react";

export const DEFAULT_DEBOUNCE_MS = 300;

/**
 * Returns `value`, but only after it has stopped changing for `delayMs`.
 *
 * The first render returns `value` immediately, so initial loads are not
 * delayed. Each change restarts the timer, so a burst of rapid changes
 * produces a single update once things settle.
 *
 * Changes are detected by identity (`Object.is`), so pass a primitive or a
 * stable reference. An object rebuilt every render never settles; serialize
 * it first (e.g. `JSON.stringify`).
 */
export function useDebouncedValue(value, delayMs = DEFAULT_DEBOUNCE_MS) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeoutId = setTimeout(() => setDebouncedValue(value), delayMs);
    return () => clearTimeout(timeoutId);
  }, [value, delayMs]);

  return debouncedValue;
}
