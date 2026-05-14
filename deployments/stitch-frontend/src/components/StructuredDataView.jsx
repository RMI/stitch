import { FIELD_META } from "../constants/fieldMeta";
import { isPrimitive } from "../utils/resourceDisplay";

const MAX_TABLE_COLUMNS = 8;

function formatLabel(key) {
  if (FIELD_META[key]?.label) return FIELD_META[key].label;

  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/\bid\b/gi, "ID")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function summarizeValue(value) {
  if (Array.isArray(value)) {
    return `${value.length} ${value.length === 1 ? "record" : "records"}`;
  }

  if (value && typeof value === "object") {
    const count = Object.keys(value).length;
    return `${count} ${count === 1 ? "field" : "fields"}`;
  }

  return formatValue(value);
}

function ValueText({ value }) {
  const display = formatValue(value);
  const isUrl = typeof value === "string" && /^https?:\/\//i.test(value);

  if (isUrl) {
    return (
      <a
        href={value}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-primary underline"
      >
        {value}
      </a>
    );
  }

  return (
    <span className={display === "—" ? "text-ink-muted" : "text-ink"}>
      {display}
    </span>
  );
}

function getSnapshotKey(item, index) {
  if (
    item &&
    typeof item === "object" &&
    !Array.isArray(item) &&
    item.id != null
  ) {
    return item.id;
  }

  // Nested arrays render as read-only snapshots, so position is the fallback.
  return `snapshot-${index}`;
}

function getHeadingTag(headingLevel, depth) {
  const baseLevel = Number.isInteger(headingLevel) ? headingLevel : 3;
  const level = Math.min(Math.max(baseLevel, 1) + depth, 6);
  return `h${level}`;
}

function ObjectFields({ entries }) {
  if (!entries.length) return null;

  return (
    <dl className="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([key, value]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {formatLabel(key)}
          </dt>
          <dd className="mt-1 break-words text-sm text-ink">
            <ValueText value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function getPrimitiveColumns(rows) {
  const columns = [];

  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (!isPrimitive(value) || columns.includes(key)) continue;
      columns.push(key);
    }
  }

  return columns;
}

function DataTable({ rows, columns, depth, headingLevel }) {
  const tableColumns = columns ?? getPrimitiveColumns(rows);

  if (!tableColumns.length) {
    return (
      <div className="space-y-3">
        {rows.map((row, index) => (
          <StructuredDataInner
            key={getSnapshotKey(row, index)}
            data={row}
            depth={depth + 1}
            headingLevel={headingLevel}
          />
        ))}
      </div>
    );
  }

  const columnSet = new Set(tableColumns);
  const detailColumns = rows.map((row) =>
    Object.entries(row).filter(
      ([key, value]) => !columnSet.has(key) && !isPrimitive(value),
    ),
  );
  const hasDetails = detailColumns.some((details) => details.length > 0);

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-panel">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs font-semibold text-ink-muted">
          <tr>
            {tableColumns.map((column) => (
              <th key={column} className="px-3 py-2">
                {formatLabel(column)}
              </th>
            ))}
            {hasDetails ? <th className="px-3 py-2">Details</th> : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, rowIndex) => {
            const details = detailColumns[rowIndex];

            return (
              <tr key={getSnapshotKey(row, rowIndex)}>
                {tableColumns.map((column) => (
                  <td key={column} className="max-w-64 px-3 py-2 align-top">
                    <ValueText value={row[column]} />
                  </td>
                ))}
                {hasDetails ? (
                  <td className="px-3 py-2 align-top text-ink-muted">
                    {details
                      .map(
                        ([key, value]) =>
                          `${formatLabel(key)}: ${summarizeValue(value)}`,
                      )
                      .join("; ")}
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StructuredDataInner({ data, depth = 0, headingLevel = 3 }) {
  if (isPrimitive(data)) {
    return <ValueText value={data} />;
  }

  if (Array.isArray(data)) {
    if (!data.length) {
      return <p className="text-sm text-ink-muted">No records.</p>;
    }

    const objectRows = data.every(
      (item) => item && typeof item === "object" && !Array.isArray(item),
    );

    if (objectRows) {
      const primitiveColumns = getPrimitiveColumns(data);

      if (
        primitiveColumns.length > 0 &&
        primitiveColumns.length <= MAX_TABLE_COLUMNS
      ) {
        return (
          <DataTable
            rows={data}
            columns={primitiveColumns}
            depth={depth}
            headingLevel={headingLevel}
          />
        );
      }
    }

    const HeadingTag = getHeadingTag(headingLevel, depth);

    return (
      <div className="space-y-3">
        {data.map((item, index) => (
          <section
            key={getSnapshotKey(item, index)}
            className="min-w-0 border-t border-line pt-3 first:border-t-0 first:pt-0"
          >
            <HeadingTag className="mb-2 text-sm font-semibold text-ink">
              Record {index + 1}
            </HeadingTag>
            <StructuredDataInner
              data={item}
              depth={depth + 1}
              headingLevel={headingLevel}
            />
          </section>
        ))}
      </div>
    );
  }

  const entries = Object.entries(data);
  const primitiveEntries = entries.filter(([, value]) => isPrimitive(value));
  const nestedEntries = entries.filter(([, value]) => !isPrimitive(value));
  const HeadingTag = getHeadingTag(headingLevel, depth);

  return (
    <div className="min-w-0 space-y-4">
      <ObjectFields entries={primitiveEntries} />

      {nestedEntries.map(([key, value]) => (
        <section key={key} className="min-w-0 border-t border-line pt-4">
          <HeadingTag className="mb-3 text-sm font-semibold text-ink">
            {formatLabel(key)}
          </HeadingTag>
          <StructuredDataInner
            data={value}
            depth={depth + 1}
            headingLevel={headingLevel}
          />
        </section>
      ))}
    </div>
  );
}

export default function StructuredDataView({
  data,
  label,
  emptyMessage = "No data available.",
  headingLevel = 3,
  className = "",
}) {
  if (data === null || data === undefined) {
    return (
      <p className={`text-sm text-ink-muted ${className}`}>{emptyMessage}</p>
    );
  }

  return (
    <div aria-label={label} className={`min-w-0 text-ink ${className}`}>
      <StructuredDataInner data={data} headingLevel={headingLevel} />
    </div>
  );
}
