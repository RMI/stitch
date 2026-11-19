// A native <select> styled like FilterDropdown's button -- same height,
// weight, border, hover and ▼ glyph -- so a filter and a plain choice sitting
// side by side read as the same kind of control. The browser's own arrow is
// hidden (appearance-none) in favour of the glyph. The right padding leaves the
// same 6px between text and glyph as the button, and keeps the select narrow
// enough to sit beside the Status filter in the Merge Review queue.
export default function Select({ className = "", children, ...props }) {
  return (
    <div className={`relative ${className}`}>
      <select
        {...props}
        className="min-h-9 w-full cursor-pointer appearance-none rounded-md border border-line bg-panel py-1.5 pr-6 pl-3 text-sm font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2"
      >
        {children}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-ink"
      >
        ▼
      </span>
    </div>
  );
}
