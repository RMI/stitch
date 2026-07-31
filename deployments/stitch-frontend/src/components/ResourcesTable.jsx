import { useState } from "react";
import { Link } from "react-router-dom";
import SourceMixBar from "./SourceMixBar";
import { getResourceField } from "../utils/resourceDisplay";
import { getCountryName } from "../constants/countries";

// sortType: "string" | "number", omit sortable (or set false) to disable sorting for a column.
// format: optional (value) => displayValue applied to the cell's raw value.
const COLUMNS = [
  {
    label: "Name",
    key: "name",
    className: "font-semibold text-ink",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Country",
    key: "country",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
    format: getCountryName,
  },
  {
    label: "State/Province",
    key: "state_province",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Region",
    key: "region",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Basin",
    key: "basin",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Field status",
    key: "field_status",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
  {
    label: "Primary hydrocarbon group",
    key: "primary_hydrocarbon_group",
    className: "text-ink-muted",
    sortable: true,
    sortType: "string",
  },
];

function SortIndicator({ column, sortConfig }) {
  if (sortConfig.column !== column) {
    return <span className="ml-1 text-line-strong">↕</span>;
  }
  return (
    <span className="ml-1 text-ink">
      {sortConfig.direction === "asc" ? "▲" : "▼"}
    </span>
  );
}

// A neutral bar in place of each cell's value. Not a text/shimmer skeleton to
// avoid dozens of animated elements across a full page of rows/columns; a
// static bar is enough to hold the row's height and shape while data loads.
// h-15.25 (61px) matches a typical populated row's height.
function SkeletonCell() {
  return (
    <td className="h-15.25 px-3 py-2.5 align-middle">
      <div className="h-4 w-3/4 rounded bg-line/60" />
    </td>
  );
}

function SkeletonRow() {
  return (
    <tr data-testid="resource-skeleton-row" className="border-b border-line/70">
      {COLUMNS.map((col) => (
        <SkeletonCell key={col.key} />
      ))}
      <td className="h-15.25 px-3 py-2.5 align-middle">
        <div className="h-4 w-full rounded bg-line/60" />
      </td>
    </tr>
  );
}

export default function ResourcesTable({
  resources,
  sortConfig,
  onSort,
  isLoading,
}) {
  const hasRows = resources?.length > 0;

  // Remembers the last confirmed row count, so a refetch (e.g. after
  // narrowing a filter) shows as many skeleton rows as the user was already
  // looking at, rather than a fixed page size. Updated whenever the query
  // has settled (not just when there are rows), so a confirmed empty result
  // is remembered as 0 rather than leaving a stale nonzero count in place
  // for the next fetch. Stays 0 until the first load settles, so the very
  // first load shows no skeleton at all.
  // Setting state during render (rather than in an effect) is the pattern
  // React recommends for deriving a value from a prop change with no extra
  // render/flash: https://react.dev/reference/react/useState#storing-information-from-previous-renders
  const [lastRowCount, setLastRowCount] = useState(0);
  const confirmedRowCount = resources?.length ?? 0;
  if (!isLoading && confirmedRowCount !== lastRowCount) {
    setLastRowCount(confirmedRowCount);
  }

  const showSkeleton = isLoading && !hasRows && lastRowCount > 0;

  if (!hasRows && !showSkeleton) return null;

  function handleSort(key) {
    onSort({
      column: key,
      direction:
        sortConfig.column === key && sortConfig.direction === "asc"
          ? "desc"
          : "asc",
    });
  }

  const sorted = resources;

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-panel">
      <table className="w-full text-sm" aria-busy={showSkeleton || undefined}>
        {showSkeleton && (
          <caption className="sr-only">Loading resources...</caption>
        )}
        <thead className="bg-surface">
          <tr className="border-b border-line text-left text-xs font-semibold tracking-wide text-ink-muted">
            {COLUMNS.map((col) =>
              col.sortable ? (
                <th
                  key={col.key}
                  className="px-3 py-2"
                  aria-sort={
                    sortConfig.column !== col.key
                      ? "none"
                      : sortConfig.direction === "asc"
                        ? "ascending"
                        : "descending"
                  }
                >
                  <button
                    onClick={() => handleSort(col.key)}
                    className="cursor-pointer select-none rounded-sm hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  >
                    {col.label}
                    <SortIndicator column={col.key} sortConfig={sortConfig} />
                  </button>
                </th>
              ) : (
                <th key={col.key} className="px-3 py-2">
                  {col.label}
                </th>
              ),
            )}
            <th className="min-w-36 px-3 py-2">Data source mix</th>
          </tr>
        </thead>
        <tbody aria-hidden={showSkeleton || undefined}>
          {showSkeleton
            ? Array.from({ length: lastRowCount }, (_, index) => (
                <SkeletonRow key={index} />
              ))
            : sorted.map((resource) => (
                // `relative` on <tr> anchors the Link's ::after pseudo-element,
                // which stretches across the full row for pointer/keyboard/right-click support.
                <tr
                  key={resource.id}
                  className="relative border-b border-line/70 transition-colors hover:bg-surface"
                >
                  {COLUMNS.map((col) => {
                    const rawValue = getResourceField(resource, col.key);
                    const value =
                      col.format && rawValue != null
                        ? col.format(rawValue)
                        : rawValue;

                    return (
                      <td
                        key={col.key}
                        className={`px-3 py-2.5 ${col.className}`}
                      >
                        {col.key === "name" ? (
                          <Link
                            to={`/oil-gas-fields/${resource.id}`}
                            className="rounded-sm text-ink underline-offset-4 after:absolute after:inset-0 after:content-[''] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                          >
                            {value ?? <span className="text-ink-muted">—</span>}
                          </Link>
                        ) : (
                          (value ?? <span className="text-ink-muted">—</span>)
                        )}
                      </td>
                    );
                  })}

                  <td className="px-3 py-2.5">
                    <SourceMixBar provenance={resource.provenance} />
                  </td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
