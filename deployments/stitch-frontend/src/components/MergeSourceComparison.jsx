import { useState } from "react";
import { useConfig } from "../config/useConfig";
import { useAuthenticatedQuery } from "../hooks/useAuthenticatedQuery";
import { getResourceDetail } from "../queries/api";
import {
  FIELD_META,
  MERGE_COMPARISON_CORE_FIELDS,
  MERGE_COMPARISON_OTHER_FIELDS,
} from "../constants/fieldMeta";
import { getRowStatus, isEmptyValue } from "../utils/mergeComparison";

// Color is never the only signal: each status pairs its strip color with an
// icon (aria-hidden) and a text label.
const STATUS_META = {
  match: {
    borderClass: "border-l-success",
    cueClass: "text-success-strong",
    icon: "✓",
    label: "Match",
  },
  differs: {
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

function gridColumnsStyle(count) {
  return { gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` };
}

function ComparisonCell({ value, status }) {
  const meta = STATUS_META[status];

  return (
    <div
      className={`min-w-0 rounded-md border border-line border-l-4 bg-panel px-3 py-2 ${meta.borderClass}`}
    >
      <div className="break-words text-sm text-ink">
        {isEmptyValue(value) ? (
          <span className="text-ink-muted">—</span>
        ) : (
          String(value)
        )}
      </div>
      <div className={`mt-1 text-xs font-medium ${meta.cueClass}`}>
        {meta.icon ? <span aria-hidden="true">{meta.icon} </span> : null}
        <span>{meta.label}</span>
      </div>
    </div>
  );
}

function ComparisonRow({ fieldKey, details }) {
  const values = details.map((detail) => detail?.data?.[fieldKey]);
  const rowStatus = getRowStatus(values);

  return (
    <div
      role="group"
      aria-label={FIELD_META[fieldKey].label}
      className="min-w-0"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {FIELD_META[fieldKey].label}
      </p>
      <div className="grid gap-3" style={gridColumnsStyle(values.length)}>
        {values.map((value, index) => (
          <ComparisonCell
            key={index}
            value={value}
            status={isEmptyValue(value) ? "empty" : rowStatus}
          />
        ))}
      </div>
    </div>
  );
}

function OtherAttributesAccordion({ details }) {
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
              details={details}
            />
          ))}
        </div>
      ) : null}
    </details>
  );
}

// Read-only, side-by-side comparison of a merge candidate's source resources.
// One aggregate query fetches every resource detail so all columns arrive
// (and error) together.
export default function MergeSourceComparison({ endpoint, resourceIds }) {
  const config = useConfig();
  const ids = resourceIds ?? [];
  const hasEnoughSources = ids.length >= 2;

  const {
    data: details,
    isLoading,
    isError,
    error,
  } = useAuthenticatedQuery({
    queryKey: [endpoint, "merge-source-details", ...ids],
    queryFn: (fetcher) =>
      Promise.all(
        ids.map((id) => getResourceDetail(config, id, fetcher, endpoint)),
      ),
    enabled: hasEnoughSources,
  });

  return (
    <section className="border-t border-line px-5 py-5">
      <h3 className="text-base font-semibold text-ink">Source comparison</h3>

      <div className="mt-3">
        {!hasEnoughSources ? (
          <p className="text-sm text-ink-muted">
            At least two source resources are required to compare.
          </p>
        ) : isLoading ? (
          <p className="text-sm text-ink-muted">Loading source resources…</p>
        ) : isError ? (
          <p className="text-sm text-danger">
            {error?.message ?? "Failed to load source resources."}
          </p>
        ) : details ? (
          <div className="space-y-4">
            <div className="grid gap-3" style={gridColumnsStyle(ids.length)}>
              {ids.map((id) => (
                <p
                  key={id}
                  className="min-w-0 break-words text-sm font-semibold text-ink"
                >
                  Resource #{id}
                </p>
              ))}
            </div>
            {MERGE_COMPARISON_CORE_FIELDS.map((fieldKey) => (
              <ComparisonRow
                key={fieldKey}
                fieldKey={fieldKey}
                details={details}
              />
            ))}
            <OtherAttributesAccordion details={details} />
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No source resources loaded.</p>
        )}
      </div>
    </section>
  );
}
