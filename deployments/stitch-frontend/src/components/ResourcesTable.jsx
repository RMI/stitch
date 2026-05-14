import { Link } from "react-router-dom";
import SourceMixBar from "./SourceMixBar";
import { getResourceField } from "../utils/resourceDisplay";

// sortType: "string" | "number", omit sortable (or set false) to disable sorting for a column.
const COLUMNS = [
  {
    label: "Name",
    key: "name",
    className: "font-semibold text-ink",
    sortable: true,
    sortType: "string",
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

export default function ResourcesTable({ resources, sortConfig, onSort }) {
  if (!resources?.length) return null;

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
      <table className="w-full text-sm">
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
        <tbody>
          {sorted.map((resource) => (
            // `relative` on <tr> anchors the Link's ::after pseudo-element,
            // which stretches across the full row for pointer/keyboard/right-click support.
            <tr
              key={resource.id}
              className="relative border-b border-line/70 transition-colors hover:bg-surface"
            >
              {COLUMNS.map((col) => {
                const value = getResourceField(resource, col.key);

                return (
                  <td key={col.key} className={`px-3 py-2.5 ${col.className}`}>
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
