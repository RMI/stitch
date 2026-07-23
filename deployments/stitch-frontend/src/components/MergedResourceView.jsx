import { useState } from "react";
import { useConfig } from "../config/useConfig";
import { useAuthenticatedQuery } from "../hooks/useAuthenticatedQuery";
import { getResourceDetail } from "../queries/api";
import {
  FIELD_META,
  MERGE_COMPARISON_CORE_FIELDS,
  MERGE_COMPARISON_OTHER_FIELDS,
} from "../constants/fieldMeta";
import { isEmptyValue } from "../utils/mergeComparison";

function MergedFieldRow({ fieldKey, value }) {
  return (
    <div
      role="group"
      aria-label={FIELD_META[fieldKey].label}
      className="min-w-0"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {FIELD_META[fieldKey].label}
      </p>
      <div className="min-w-0 rounded-md border border-line bg-panel px-3 py-2">
        <div className="break-words text-sm text-ink">
          {isEmptyValue(value) ? (
            <span className="text-ink-muted">—</span>
          ) : (
            String(value)
          )}
        </div>
      </div>
    </div>
  );
}

function OtherAttributesAccordion({ detail }) {
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
            <MergedFieldRow
              key={fieldKey}
              fieldKey={fieldKey}
              value={detail?.data?.[fieldKey]}
            />
          ))}
        </div>
      ) : null}
    </details>
  );
}

// Read-only view of the resource a merge candidate produced, shown in place of
// the source comparison once the merge has run.
export default function MergedResourceView({ endpoint, resourceId }) {
  const config = useConfig();

  const {
    data: detail,
    isLoading,
    isError,
    error,
  } = useAuthenticatedQuery({
    queryKey: [endpoint, "merged-resource-detail", resourceId],
    queryFn: (fetcher) =>
      getResourceDetail(config, resourceId, fetcher, endpoint),
    enabled: Boolean(resourceId),
  });

  return (
    <section className="border-t border-line px-5 py-5">
      <h3 className="text-base font-semibold text-ink">Merged resource</h3>

      <div className="mt-3">
        {isLoading ? (
          <p className="text-sm text-ink-muted">Loading merged resource…</p>
        ) : isError ? (
          <p className="text-sm text-danger">
            {error?.message ?? "Failed to load merged resource."}
          </p>
        ) : detail ? (
          <div className="space-y-4">
            {MERGE_COMPARISON_CORE_FIELDS.map((fieldKey) => (
              <MergedFieldRow
                key={fieldKey}
                fieldKey={fieldKey}
                value={detail.data?.[fieldKey]}
              />
            ))}
            <OtherAttributesAccordion detail={detail} />
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No merged resource loaded.</p>
        )}
      </div>
    </section>
  );
}
