import { FIELD_META } from "../constants/fieldMeta";

const MAX_TABLE_COLUMNS = 8;

function isPrimitive(value) {
  return (
    value == null || ["string", "number", "boolean"].includes(typeof value)
  );
}

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
      if (columns.length >= MAX_TABLE_COLUMNS) return columns;
    }
  }

  return columns;
}

function DataTable({ rows }) {
  const columns = getPrimitiveColumns(rows);

  if (!columns.length) {
    return (
      <div className="space-y-3">
        {rows.map((row, index) => (
          <StructuredDataInner key={index} data={row} depth={1} />
        ))}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-panel">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs font-semibold text-ink-muted">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2">
                {formatLabel(column)}
              </th>
            ))}
            {rows.some((row) =>
              Object.entries(row).some(
                ([key, value]) => !columns.includes(key) && !isPrimitive(value),
              ),
            ) ? (
              <th className="px-3 py-2">Details</th>
            ) : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column} className="max-w-64 px-3 py-2 align-top">
                  <ValueText value={row[column]} />
                </td>
              ))}
              {Object.entries(row).some(
                ([key, value]) => !columns.includes(key) && !isPrimitive(value),
              ) ? (
                <td className="px-3 py-2 align-top text-ink-muted">
                  {Object.entries(row)
                    .filter(
                      ([key, value]) =>
                        !columns.includes(key) && !isPrimitive(value),
                    )
                    .map(
                      ([key, value]) =>
                        `${formatLabel(key)}: ${summarizeValue(value)}`,
                    )
                    .join("; ")}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StructuredDataInner({ data, depth = 0 }) {
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
      const primitiveColumnCount = getPrimitiveColumns(data).length;

      if (
        primitiveColumnCount > 0 &&
        primitiveColumnCount <= MAX_TABLE_COLUMNS
      ) {
        return <DataTable rows={data} />;
      }
    }

    return (
      <div className="space-y-3">
        {data.map((item, index) => (
          <section
            key={index}
            className="min-w-0 border-t border-line pt-3 first:border-t-0 first:pt-0"
          >
            <h4 className="mb-2 text-sm font-semibold text-ink">
              Record {index + 1}
            </h4>
            <StructuredDataInner data={item} depth={depth + 1} />
          </section>
        ))}
      </div>
    );
  }

  const entries = Object.entries(data);
  const primitiveEntries = entries.filter(([, value]) => isPrimitive(value));
  const nestedEntries = entries.filter(([, value]) => !isPrimitive(value));

  return (
    <div className="min-w-0 space-y-4">
      <ObjectFields entries={primitiveEntries} />

      {nestedEntries.map(([key, value]) => (
        <section key={key} className="min-w-0 border-t border-line pt-4">
          <h4 className="mb-3 text-sm font-semibold text-ink">
            {formatLabel(key)}
          </h4>
          <StructuredDataInner data={value} depth={depth + 1} />
        </section>
      ))}
    </div>
  );
}

export default function StructuredDataView({
  data,
  label,
  emptyMessage = "No data available.",
  className = "",
}) {
  if (data === null || data === undefined) {
    return (
      <p className={`text-sm text-ink-muted ${className}`}>{emptyMessage}</p>
    );
  }

  return (
    <div aria-label={label} className={`min-w-0 text-ink ${className}`}>
      <StructuredDataInner data={data} />
    </div>
  );
}
