import { useState } from "react";
import {
  FIELD_META,
  MERGE_COMPARISON_CORE_FIELDS,
  MERGE_COMPARISON_OTHER_FIELDS,
} from "../constants/fieldMeta";
import { compareEntry, valueEntryForResource } from "../utils/candidateCompare";
import SourceMixBar from "./SourceMixBar";

// Color is never the only signal: each status pairs its strip color with an
// icon (aria-hidden) and a text label. "match"/"different" mirror the backend
// status values; "empty" is local to the UI for cells and rows where no
// source has a value.
const STATUS_META = {
  match: {
    borderClass: "border-l-success",
    cueClass: "text-success-strong",
    icon: "✓",
    label: "Match",
  },
  different: {
    borderClass: "border-l-warning",
    cueClass: "text-warning",
    icon: "≠",
    label: "Differs",
  },
  empty: {
    borderClass: "border-l-line",
    cueClass: "text-ink-muted",
    icon: null,
    label: "No value",
  },
};

// Shared by ComparisonCell and ComparisonSkeletonCell so the loading grid and
// the loaded grid cannot drift apart in size.
const CELL_BOX_CLASSES =
  "min-w-0 rounded-md border border-line border-l-4 bg-panel px-3 py-2";

function gridColumnsStyle(count) {
  return { gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` };
}

// The backend omits null values entirely, so a missing valueEntry means the
// resource has no value ("empty" status). An empty string is a real value
// with a real status; it just has nothing visible to print, so the dash for
// it is display-only.
function ComparisonCell({ valueEntry, status }) {
  const meta = STATUS_META[status];
  const value = valueEntry?.value;
  const hasVisibleValue = value != null && value !== "";

  return (
    <div className={`${CELL_BOX_CLASSES} ${meta.borderClass}`}>
      <div className="break-words text-sm text-ink">
        {hasVisibleValue ? (
          String(value)
        ) : (
          <span className="text-ink-muted">—</span>
        )}
      </div>
      <div className={`mt-1 text-xs font-medium ${meta.cueClass}`}>
        {meta.icon ? <span aria-hidden="true">{meta.icon} </span> : null}
        <span>{meta.label}</span>
      </div>
    </div>
  );
}

function ComparisonRow({ fieldKey, entry, resourceIds }) {
  const isEmptyRow = !entry || entry.values.length === 0;

  return (
    <div
      role="group"
      aria-label={FIELD_META[fieldKey].label}
      className="min-w-0"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {FIELD_META[fieldKey].label}
      </p>
      <div className="grid gap-3" style={gridColumnsStyle(resourceIds.length)}>
        {resourceIds.map((id) => {
          const valueEntry = isEmptyRow
            ? null
            : valueEntryForResource(entry, id);
          return (
            <ComparisonCell
              key={id}
              valueEntry={valueEntry}
              status={valueEntry ? entry.status : "empty"}
            />
          );
        })}
      </div>
    </div>
  );
}

// A loading cell keeps the empty cell's box and neutral left edge, with a
// spinner where the value will land. The value row is pinned to h-5 — the
// text-sm line height of a loaded value — and the status cue is reserved but
// blank, so the cell is exactly the height of a loaded one. The cue stays blank
// on purpose: a loading cell has no status yet, and "No value" would be false.
function ComparisonSkeletonCell() {
  return (
    <div
      data-testid="comparison-skeleton-cell"
      className={`${CELL_BOX_CLASSES} ${STATUS_META.empty.borderClass}`}
    >
      <div className="flex h-5 items-center">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-ink-muted motion-reduce:animate-none" />
      </div>
      <div className="mt-1 text-xs">&nbsp;</div>
    </div>
  );
}

// Which data sources a resource's values come from, under its column heading:
// the same compact bar the Resource List's "Data source mix" column shows.
// `sourceDetails` is the caller's query of the resources' detail views, in
// resourceIds order; without it nothing is shown. While it loads, a grey bar
// the same height as the loaded one keeps the rows below from shifting.
function ColumnSourceMix({ sourceDetails, index }) {
  if (!sourceDetails) return null;

  if (sourceDetails.isError) {
    return (
      <p className="mt-1 text-xs leading-4 text-ink-muted">
        Source mix unavailable
      </p>
    );
  }

  if (sourceDetails.isLoading || !sourceDetails.data) {
    return (
      <div
        data-testid="source-mix-placeholder"
        aria-hidden="true"
        className="mt-1"
      >
        <div className="h-4 w-full rounded-sm bg-surface-tint ring-1 ring-line" />
        <div className="mt-1 h-4" />
      </div>
    );
  }

  return (
    <div className="mt-1">
      <SourceMixBar provenance={sourceDetails.data[index]?.provenance} />
    </div>
  );
}

// One column heading: the resource id, then its source mix.
function ColumnHeader({ resourceId, sourceDetails, index }) {
  return (
    <div className="min-w-0">
      <p className="break-words text-sm font-semibold text-ink">
        Resource #{resourceId}
      </p>
      <ColumnSourceMix sourceDetails={sourceDetails} index={index} />
    </div>
  );
}

// The loaded layout with placeholders in the cells. Headers and field labels are
// real: resourceIds is a prop and FIELD_META is static, so neither changes when
// the data lands. The trailing bar stands in for the collapsed accordion summary.
function ComparisonSkeleton({ resourceIds, sourceDetails }) {
  return (
    <div aria-hidden="true" className="space-y-4">
      <div className="grid gap-3" style={gridColumnsStyle(resourceIds.length)}>
        {resourceIds.map((id, index) => (
          <ColumnHeader
            key={id}
            resourceId={id}
            sourceDetails={sourceDetails}
            index={index}
          />
        ))}
      </div>

      {MERGE_COMPARISON_CORE_FIELDS.map((fieldKey) => (
        <div key={fieldKey} className="min-w-0">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {FIELD_META[fieldKey].label}
          </p>
          <div
            className="grid gap-3"
            style={gridColumnsStyle(resourceIds.length)}
          >
            {resourceIds.map((id) => (
              <ComparisonSkeletonCell key={id} />
            ))}
          </div>
        </div>
      ))}

      <div className="border-t border-line pt-4">
        <p className="text-sm font-semibold text-ink">
          Other attributes ({MERGE_COMPARISON_OTHER_FIELDS.length})
        </p>
      </div>
    </div>
  );
}

function OtherAttributesAccordion({ compare, resourceIds }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <details
      open={isOpen}
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
      className="border-t border-line pt-4"
    >
      <summary className="cursor-pointer text-sm font-semibold text-ink">
        Other attributes ({MERGE_COMPARISON_OTHER_FIELDS.length})
      </summary>
      {isOpen ? (
        <div className="mt-4 space-y-4">
          {MERGE_COMPARISON_OTHER_FIELDS.map((fieldKey) => (
            <ComparisonRow
              key={fieldKey}
              fieldKey={fieldKey}
              entry={compareEntry(compare, fieldKey)}
              resourceIds={resourceIds}
            />
          ))}
        </div>
      ) : null}
    </details>
  );
}

// Read-only, side-by-side comparison of a merge candidate's source resources,
// rendered from the backend `compare` object on the candidate detail response.
// Statuses come verbatim from the backend; this component performs no value
// comparison of its own. Loading and error state belong to the caller's
// detail query, and the per-column source mix to the caller's
// `sourceDetails` query.
export default function MergeSourceComparison({
  resourceIds,
  compare,
  isLoading,
  isError,
  error,
  sourceDetails,
}) {
  const ids = resourceIds ?? [];
  const hasEnoughSources = ids.length >= 2;

  return (
    <section className="border-t border-line px-5 py-5">
      <h3 className="text-base font-semibold text-ink">Source comparison</h3>

      <div className="mt-3">
        {!hasEnoughSources ? (
          <p className="text-sm text-ink-muted">
            At least two source resources are required to compare.
          </p>
        ) : isLoading ? (
          <div aria-busy="true">
            <p className="sr-only">Loading comparison…</p>
            <ComparisonSkeleton
              resourceIds={ids}
              sourceDetails={sourceDetails}
            />
          </div>
        ) : isError ? (
          <p className="text-sm text-danger">
            {error?.message ?? "Failed to load comparison."}
          </p>
        ) : compare ? (
          <div className="space-y-4">
            <div className="grid gap-3" style={gridColumnsStyle(ids.length)}>
              {ids.map((id, index) => (
                <ColumnHeader
                  key={id}
                  resourceId={id}
                  sourceDetails={sourceDetails}
                  index={index}
                />
              ))}
            </div>
            {MERGE_COMPARISON_CORE_FIELDS.map((fieldKey) => (
              <ComparisonRow
                key={fieldKey}
                fieldKey={fieldKey}
                entry={compareEntry(compare, fieldKey)}
                resourceIds={ids}
              />
            ))}
            <OtherAttributesAccordion compare={compare} resourceIds={ids} />
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No comparison available.</p>
        )}
      </div>
    </section>
  );
}
