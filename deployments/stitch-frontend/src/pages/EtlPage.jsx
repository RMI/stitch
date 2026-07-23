import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";
import Input from "../components/Input";

// Per-ETL run parameters. Empty number/text fields are omitted from the
// request body so the service falls back to its env-derived defaults.
const GEM_FIELDS = [
  {
    key: "payload_limit",
    label: "Payload limit",
    type: "number",
    help: "Optional cap on payloads posted this run. Leave blank to post all.",
  },
  {
    key: "gem_xlsx_sheet",
    label: "GEM xlsx sheet",
    type: "text",
    placeholder: "Main data",
    help: "Excel sheet name to load. Leave blank to use the configured default.",
  },
];

const CCR_FIELDS = [
  {
    key: "payload_limit",
    label: "Payload limit",
    type: "number",
    help: "Optional cap on payloads posted this run. Leave blank to post all.",
  },
  {
    key: "xlsx_sheet",
    label: "CCR xlsx sheet",
    type: "text",
    placeholder: "Reservoirs",
    help: "Excel sheet name to load. Leave blank to use the configured default.",
  },
];

const BC_FIELDS = [
  {
    key: "payload_limit",
    label: "Payload limit",
    type: "number",
    help: "Optional cap on payloads posted this run. Leave blank to post all.",
  },
  {
    key: "xlsx_sheet",
    label: "BC xlsx sheet",
    type: "text",
    placeholder: "Reservoirs",
    help: "Excel sheet name to load. Leave blank to use the configured default.",
  },
];

const ALB_FIELDS = [
  {
    key: "payload_limit",
    label: "Payload limit",
    type: "number",
    help: "Optional cap on payloads posted this run. Leave blank to post all.",
  },
  {
    key: "xlsx_sheet",
    label: "Alberta xlsx sheet",
    type: "text",
    placeholder: "Reservoirs",
    help: "Excel sheet name to load. Leave blank to use the configured default.",
  },
];

const WOODMAC_FIELDS = [
  {
    key: "payload_limit",
    label: "Payload limit",
    type: "number",
    help: "Optional cap on payloads posted this run. Leave blank to post all.",
  },
  {
    key: "query_limit",
    label: "Query limit",
    type: "number",
    help: "Optional cap on rows requested from the WoodMac query.",
  },
  {
    key: "use_cached",
    label: "Reuse cached WoodMac result (if within TTL)",
    type: "checkbox",
  },
];

const STATE_STYLES = {
  running: "border-warning/30 bg-warning-soft text-warning",
  succeeded: "border-success/25 bg-success-soft text-success-strong",
  failed: "border-danger/25 bg-danger-soft text-danger",
};

function StateBadge({ state }) {
  if (!state) return null;

  const classes = STATE_STYLES[state] ?? "border-line bg-surface text-ink";

  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${classes}`}
    >
      {state}
    </span>
  );
}

async function parseJsonResponse(response) {
  const text = await response.text();

  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return { raw: text };
  }
}

function EtlPanel({ title, description, baseUrl, fields, getToken }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(
      fields.map((field) => [
        field.key,
        field.type === "checkbox" ? false : "",
      ]),
    ),
  );
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);

  function setField(key, value) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function buildRequestBody() {
    const body = {};

    for (const field of fields) {
      const value = values[field.key];

      if (field.type === "checkbox") {
        body[field.key] = Boolean(value);
      } else if (value !== "" && value != null) {
        body[field.key] = field.type === "number" ? Number(value) : value;
      }
    }

    return body;
  }

  async function handleStart() {
    setStarting(true);
    setError(null);

    try {
      const token = await getToken();

      const response = await fetch(`${baseUrl}/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(buildRequestBody()),
      });

      const parsed = await parseJsonResponse(response);

      if (response.status === 409) {
        setError({
          status: 409,
          message: "A run is already in progress — refresh status to check.",
          body: parsed,
        });
        return;
      }

      if (!response.ok) {
        setError({ status: response.status, body: parsed });
        return;
      }

      setRecord(parsed);
    } catch (err) {
      setError({
        status: null,
        body: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setStarting(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);

    try {
      // GET /status is unauthenticated per the ETL OpenAPI spec.
      const response = await fetch(`${baseUrl}/status`);
      const parsed = await parseJsonResponse(response);

      if (!response.ok) {
        setError({ status: response.status, body: parsed });
        return;
      }

      setRecord(parsed);
    } catch (err) {
      setError({
        status: null,
        body: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setRefreshing(false);
    }
  }

  const isRunning = record?.state === "running";

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <StateBadge state={record?.state} />
      </div>
      <p className="mt-1 text-sm text-ink-muted">{description}</p>

      <div className="mt-4 space-y-4">
        {fields.map((field) =>
          field.type === "checkbox" ? (
            <div key={field.key}>
              <label className="flex items-center gap-3 text-sm font-medium text-ink">
                <input
                  type="checkbox"
                  checked={values[field.key]}
                  onChange={(e) => setField(field.key, e.target.checked)}
                  className="accent-primary"
                />
                <span>{field.label}</span>
              </label>
            </div>
          ) : (
            <div key={field.key}>
              <label className="block text-sm font-medium text-ink">
                <span className="mb-1 block">{field.label}</span>
                <Input
                  type={field.type}
                  value={values[field.key]}
                  onChange={(e) => setField(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  min={field.type === "number" ? 1 : undefined}
                  className="w-full"
                />
              </label>
              {field.help ? (
                <p className="mt-1 text-xs text-ink-muted">{field.help}</p>
              ) : null}
            </div>
          ),
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          onClick={handleStart}
          disabled={starting || isRunning}
          variant="primary"
        >
          {starting ? "Starting…" : "Start run"}
        </Button>
        <Button
          onClick={handleRefresh}
          disabled={refreshing}
          variant="secondary"
        >
          {refreshing ? "Refreshing…" : "Refresh status"}
        </Button>
      </div>

      {error ? (
        <div className="mt-4 rounded-md border border-danger/25 bg-danger-soft p-3 text-sm text-danger">
          {error.message ? (
            <p className="mb-2 font-medium">{error.message}</p>
          ) : null}
          <StructuredDataView
            data={{ status: error.status, response: error.body }}
            label={`${title} error`}
          />
        </div>
      ) : null}

      <div className="mt-4 border-t border-line pt-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">Run status</h3>
        {record ? (
          <StructuredDataView data={record} label={`${title} run status`} />
        ) : (
          <p className="text-sm text-ink-muted">
            No run started yet. Start a run or refresh to fetch the latest
            status.
          </p>
        )}
      </div>
    </section>
  );
}

export default function EtlPage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();

  const getToken = () =>
    getAccessTokenSilently({
      authorizationParams: { audience: config.auth0.audience },
    });

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">ETL Pipelines</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an ETL run and check its status. Only one run per pipeline may
          be active at a time.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <EtlPanel
          title="GEM"
          description="Load GEM oil & gas data from the configured spreadsheet and post it to Stitch."
          baseUrl={`${config.etlBaseUrl}/gem`}
          fields={GEM_FIELDS}
          getToken={getToken}
        />
        <EtlPanel
          title="WoodMac"
          description="Fetch WoodMac query results and post them to Stitch."
          baseUrl={`${config.etlBaseUrl}/wm`}
          fields={WOODMAC_FIELDS}
          getToken={getToken}
        />
        <EtlPanel
          title="CCR"
          description="Load C&C Reservoirs field data from the configured spreadsheet and post it to Stitch."
          baseUrl={`${config.etlBaseUrl}/ccr`}
          fields={CCR_FIELDS}
          getToken={getToken}
        />
        <EtlPanel
          title="BC"
          description="Load BC Energy Regulator field data from the configured spreadsheet and post it to Stitch."
          baseUrl={`${config.etlBaseUrl}/bc`}
          fields={BC_FIELDS}
          getToken={getToken}
        />
        <EtlPanel
          title="Alberta"
          description="Load Alberta Energy Regulator field data from the configured spreadsheet and post it to Stitch."
          baseUrl={`${config.etlBaseUrl}/alb`}
          fields={ALB_FIELDS}
          getToken={getToken}
        />
      </div>
    </div>
  );
}
