import { Link } from "react-router";
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
    return (
      <span
        aria-hidden="true"
        className="ml-1 text-[0.65rem] text-line-strong/70"
      >
        ↕
      </span>
    );
  }
  return (
    <span aria-hidden="true" className="ml-1 text-[0.65rem] text-ink">
      {sortConfig.direction === "asc" ? "▲" : "▼"}
    </span>
  );
}

// Pointer-only extension of a row's name link, so clicking, middle-clicking or
// right-clicking anywhere in the row reaches the resource. Hidden from
// assistive tech and the tab order: the name cell holds the row's one real,
// named link.
function RowLinkOverlay({ href }) {
  return (
    <Link
      to={href}
      aria-hidden="true"
      tabIndex={-1}
      className="absolute inset-0"
    />
  );
}

export default function ResourcesTable({
  resources,
  sortConfig,
  onSort,
  isFetching,
}) {
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
    <div className="relative overflow-x-auto rounded-md border border-line bg-panel">
      <table
        className={`w-full text-sm transition-opacity ${isFetching ? "pointer-events-none opacity-50" : ""}`}
        aria-busy={isFetching || undefined}
      >
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
          {sorted.map((resource) => {
            const resourceHref = `/oil-gas-fields/${resource.id}`;

            return (
              // Each cell carries its own overlay so the whole row stays
              // clickable. The overlays are deliberately anchored to the <td>s
              // rather than the <tr>: CSS 2.1 leaves `position: relative`
              // undefined on table rows and WebKit ignores it, which made every
              // row's overlay resolve against the scroll container and cover the
              // entire table (STIT-737).
              <tr
                key={resource.id}
                className="group border-b border-line/70 transition-colors hover:bg-surface"
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
                      className={`relative px-3 py-2.5 ${col.className}`}
                    >
                      {col.key === "name" ? (
                        <Link
                          to={resourceHref}
                          className="rounded-sm text-ink underline-offset-4 after:absolute after:inset-0 after:content-[''] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 group-hover:underline"
                        >
                          {value ?? <span className="text-ink-muted">—</span>}
                        </Link>
                      ) : (
                        <>
                          {value ?? <span className="text-ink-muted">—</span>}
                          <RowLinkOverlay href={resourceHref} />
                        </>
                      )}
                    </td>
                  );
                })}

                <td className="relative px-3 py-2.5">
                  <SourceMixBar provenance={resource.provenance} />
                  <RowLinkOverlay href={resourceHref} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {isFetching && (
        <div
          role="status"
          className="absolute inset-0 flex items-center justify-center"
        >
          <span className="sr-only">Updating resources...</span>
          <span
            aria-hidden="true"
            className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-ink-muted motion-reduce:animate-none"
          />
        </div>
      )}
    </div>
  );
}
