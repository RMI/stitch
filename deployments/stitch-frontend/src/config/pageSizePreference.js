/**
 * Remembers the resources list page size a user chose, for the rest of the
 * browser session (session storage is per tab and cleared when it closes).
 *
 * The URL stays the source of truth for the list view: this is only the
 * fallback used when the URL has no `page_size` -- e.g. after the Resources
 * tab or the logotype, which link to a bare `/`. See config/listParams.js.
 *
 * Storage can be unavailable (some privacy modes throw on every access), so
 * both functions treat any storage error as "nothing remembered" rather than
 * breaking the list.
 */
import { PAGE_SIZE_OPTIONS } from "../queries/resources";

export const PAGE_SIZE_STORAGE_KEY = "stitch.resources.pageSize";

// The remembered page size, or null if none (or none that is still offered).
export function getRememberedPageSize() {
  let stored;
  try {
    stored = window.sessionStorage.getItem(PAGE_SIZE_STORAGE_KEY);
  } catch {
    return null;
  }
  const value = Number(stored);
  return stored && PAGE_SIZE_OPTIONS.includes(value) ? value : null;
}

export function rememberPageSize(pageSize) {
  if (!PAGE_SIZE_OPTIONS.includes(pageSize)) return;
  try {
    window.sessionStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize));
  } catch {
    // Unavailable storage just means the choice is not remembered.
  }
}
