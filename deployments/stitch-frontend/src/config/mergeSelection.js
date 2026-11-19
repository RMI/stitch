/**
 * Remembers which resources a user has picked to propose as a merge, for the
 * rest of the browser session (session storage is per tab and cleared when it
 * closes).
 *
 * Picking a merge pair usually means opening each resource to check it really
 * is a duplicate, so the pick has to survive leaving the list and coming back.
 * Each entry keeps the name and country alongside the id, so the selection can
 * be shown by name even when the picked rows are on another page or filtered
 * out.
 *
 * Storage can be unavailable (some privacy modes throw on every access), so
 * both functions treat any storage error as "nothing remembered" rather than
 * breaking the list.
 */

function storageKey(endpoint) {
  return `stitch.${endpoint}.mergeSelection`;
}

function isSelectionEntry(entry) {
  return Number.isInteger(entry?.id);
}

// The remembered selection as [{ id, name, country }], or [] if none.
export function getRememberedMergeSelection(endpoint) {
  let stored;
  try {
    stored = JSON.parse(window.sessionStorage.getItem(storageKey(endpoint)));
  } catch {
    return [];
  }
  return Array.isArray(stored) ? stored.filter(isSelectionEntry) : [];
}

export function rememberMergeSelection(endpoint, selection) {
  try {
    if (selection.length) {
      window.sessionStorage.setItem(
        storageKey(endpoint),
        JSON.stringify(selection),
      );
    } else {
      window.sessionStorage.removeItem(storageKey(endpoint));
    }
  } catch {
    // Unavailable storage just means the selection is not remembered.
  }
}
