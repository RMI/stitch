const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

// Five-digit page numbers are wide enough that the usual window of nearby
// pages overflows the control, so past this many pages the window narrows to
// just the current page and navigation leans on the arrows (STIT-739).
const WIDE_WINDOW_MAX_PAGES = 9999;
const WIDE_WINDOW = 3;
const NARROW_WINDOW = 1;

// Always returns exactly `windowSize + 4` slots:
// [first, leftEllipsis, ...window, rightEllipsis, last]
// Near either edge the window absorbs the adjacent first/last and ellipsis
// positions, showing a contiguous run of pages instead. `windowSize` must be
// odd so the window can centre on the current page.
// Each slot is { page, visible, ellipsis }
function getSlots(currentPage, totalPages, windowSize) {
  const slot = (page, visible = true) => ({ page, visible, ellipsis: false });
  const ellipsis = (visible = true) => ({
    page: null,
    visible,
    ellipsis: true,
  });

  // Length of the contiguous run of pages shown at either edge.
  const edgeRun = windowSize + 2;
  const run = (startPage) =>
    Array.from({ length: edgeRun }, (_, i) => {
      const page = startPage + i;
      return slot(page, page >= 1 && page <= totalPages);
    });

  // Near the start, e.g. 1 2 3 4 5 … last for the wide window.
  if (currentPage < edgeRun) {
    return [
      ...run(1),
      ellipsis(totalPages > edgeRun + 1),
      slot(totalPages, totalPages > edgeRun),
    ];
  }

  // Near the end, e.g. 1 … last-4 last-3 last-2 last-1 last for the wide window.
  if (currentPage > totalPages - edgeRun + 1) {
    return [
      slot(1, totalPages > edgeRun),
      ellipsis(totalPages > edgeRun + 1),
      ...run(totalPages - edgeRun + 1),
    ];
  }

  // Middle, e.g. 1 … prev current next … last for the wide window.
  const half = (windowSize - 1) / 2;
  return [
    slot(1),
    ellipsis(),
    ...Array.from({ length: windowSize }, (_, i) =>
      slot(currentPage - half + i),
    ),
    ellipsis(),
    slot(totalPages),
  ];
}

// `shrink-0` matters: the explicit `min-w-9` below replaces flexbox's
// `min-width: auto`, which is what normally stops a flex item shrinking past
// its content. Without it a narrow viewport squeezes buttons back to 36px and
// clips the label again (STIT-739).
const buttonBase =
  "flex h-9 shrink-0 items-center justify-center rounded-md border text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2";

// The arrows hold a single glyph, so they stay square.
const navButtonBase = `${buttonBase} w-9`;

// Page buttons keep the square footprint for short numbers but grow with the
// label rather than clipping it.
const pageButtonBase = `${buttonBase} min-w-9 px-2 tabular-nums`;

export default function Pagination({
  page,
  pageSize,
  totalCount,
  totalPages,
  onPageChange,
  onPageSizeChange,
}) {
  const slots = getSlots(
    page,
    totalPages,
    totalPages > WIDE_WINDOW_MAX_PAGES ? NARROW_WINDOW : WIDE_WINDOW,
  );
  const firstItem = (page - 1) * pageSize + 1;
  const lastItem = Math.min(page * pageSize, totalCount);

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-y-3 text-sm text-ink-muted">
      <span className="font-medium">
        Showing {firstItem.toLocaleString()}–{lastItem.toLocaleString()} of{" "}
        {totalCount.toLocaleString()}
      </span>

      {totalPages > 1 && (
        <div className="flex flex-wrap items-center gap-1">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className={`${navButtonBase} border-line bg-panel text-ink hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40`}
            aria-label="Previous page"
          >
            ‹
          </button>

          {slots.map((slot, i) =>
            slot.ellipsis ? (
              <span
                key={`ellipsis-${i}`}
                style={{ visibility: slot.visible ? "visible" : "hidden" }}
                className="flex h-9 w-9 shrink-0 items-center justify-center text-ink-muted select-none"
                aria-hidden="true"
              >
                …
              </span>
            ) : (
              <button
                key={`slot-${i}`}
                onClick={() => slot.visible && onPageChange(slot.page)}
                aria-current={slot.page === page ? "page" : undefined}
                style={{ visibility: slot.visible ? "visible" : "hidden" }}
                tabIndex={slot.visible ? 0 : -1} // focusable if visible
                className={`${pageButtonBase} ${
                  slot.page === page
                    ? "border-primary bg-primary text-white"
                    : "border-line bg-panel text-ink hover:bg-surface"
                }`}
              >
                {slot.page.toLocaleString()}
              </button>
            ),
          )}

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className={`${navButtonBase} border-line bg-panel text-ink hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40`}
            aria-label="Next page"
          >
            ›
          </button>
        </div>
      )}

      <div className="flex items-center gap-2">
        <label
          htmlFor="page-size-select"
          className="font-medium text-ink-muted"
        >
          Per page:
        </label>
        <select
          id="page-size-select"
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="rounded-md border border-line bg-panel px-2 py-1 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
