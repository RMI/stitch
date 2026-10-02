/**
 * The Merge Review queue's sort, remembered for the rest of the browser
 * session (session storage is per tab and cleared when it closes), the same
 * way the Resource List remembers its page size (config/pageSizePreference.js).
 *
 * Storage can be unavailable (some privacy modes throw on every access), so
 * both functions treat any storage error as "nothing remembered" rather than
 * breaking the page.
 */

export const MERGE_REVIEW_SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "name-asc", label: "Name A–Z" },
  { value: "name-desc", label: "Name Z–A" },
  { value: "status", label: "Status" },
];

export const DEFAULT_MERGE_REVIEW_SORT = "newest";

export const MERGE_REVIEW_SORT_STORAGE_KEY = "stitch.mergeReview.sort";

const SORT_VALUES = MERGE_REVIEW_SORT_OPTIONS.map((option) => option.value);

export function getRememberedMergeReviewSort() {
  let stored;
  try {
    stored = window.sessionStorage.getItem(MERGE_REVIEW_SORT_STORAGE_KEY);
  } catch {
    return DEFAULT_MERGE_REVIEW_SORT;
  }
  return SORT_VALUES.includes(stored) ? stored : DEFAULT_MERGE_REVIEW_SORT;
}

export function rememberMergeReviewSort(sort) {
  if (!SORT_VALUES.includes(sort)) return;
  try {
    window.sessionStorage.setItem(MERGE_REVIEW_SORT_STORAGE_KEY, sort);
  } catch {
    // Unavailable storage just means the choice is not remembered.
  }
}
