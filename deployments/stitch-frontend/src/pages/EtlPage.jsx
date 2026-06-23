import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import { createAuthenticatedFetcher } from "../auth/api";
import { useJobRunner } from "../hooks/useJobRunner";
import JobTriggerButton from "../components/JobTriggerButton";
import JobResultList from "../components/JobResultList";
import LastUpdated from "../components/LastUpdated";
import StructuredDataView from "../components/StructuredDataView";
import Input from "../components/Input";

// NOTE: the ETL services aren't on the shared `stitch-jobs` framework yet. This
// UI targets that contract (POST /start, GET /status/{job_id}, GET /jobs) so it
// lights up once the backend adopts it.

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

function EtlPanel({ title, description, baseUrl, fields, fetcher }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(
      fields.map((field) => [
        field.key,
        field.type === "checkbox" ? false : "",
      ]),
    ),
  );
  const [forceRerun, setForceRerun] = useState(false);
  const [revealed, setRevealed] = useState(false);

  // Look up this pipeline's runs with default params (a stable key, so editing
  // the tunable fields doesn't refetch on every keystroke). The pipeline is its
  // own service, so /find returns its runs per the backend's dedup policy.
  const job = useJobRunner({ baseUrl, fetcher, lookupBody: {} });

  function setField(key, value) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function buildRequestBody() {
    const body = { force: forceRerun };

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

  async function handleTrigger() {
    // A recent run exists and we're not forcing → just reveal it.
    if (job.hasExisting && !forceRerun && !revealed) {
      setRevealed(true);
      return;
    }
    setRevealed(true);
    await job.start(buildRequestBody());
    setForceRerun(false);
  }

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <LastUpdated at={job.lastUpdatedAt} />
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
                  disabled={job.isRunning}
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
                  disabled={job.isRunning}
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

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <JobTriggerButton
          running={job.isRunning}
          force={forceRerun}
          hasExisting={job.hasExisting}
          revealed={revealed}
          labels={{
            running: "Running…",
            show: "Show result",
            create: "Start run",
            recreate: "Re-run",
          }}
          onClick={handleTrigger}
          variant="primary"
        />
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={forceRerun}
            onChange={(e) => setForceRerun(e.target.checked)}
            disabled={job.isRunning}
            className="accent-primary"
          />
          <span>Re-run (ignore a recent run)</span>
        </label>
      </div>

      {job.error ? (
        <div className="mt-4 rounded-md border border-danger/25 bg-danger-soft p-3 text-sm text-danger">
          {job.error}
        </div>
      ) : null}

      <div className="mt-4 border-t border-line pt-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">Runs</h3>
        {revealed && job.records.length ? (
          <JobResultList
            records={job.records}
            renderResult={(record) =>
              record.state === "succeeded" ? (
                <StructuredDataView
                  data={record.result}
                  label={`${title} run result`}
                />
              ) : record.state === "failed" ? (
                <p className="text-sm text-danger">
                  {record.error || "Run failed."}
                </p>
              ) : (
                <p className="text-sm text-ink-muted">Running…</p>
              )
            }
          />
        ) : (
          <p className="text-sm text-ink-muted">
            No run started yet. Start a run to begin.
          </p>
        )}
      </div>
    </section>
  );
}

export default function EtlPage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const fetcher = createAuthenticatedFetcher(config, getAccessTokenSilently);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">ETL Pipelines</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an ETL run and watch its status. A recent run for a pipeline is
          shown rather than started again; use “Re-run” to force a fresh run.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <EtlPanel
          title="GEM"
          description="Load GEM oil & gas data from the configured spreadsheet and post it to Stitch."
          baseUrl={config.etlGemBaseUrl}
          fields={GEM_FIELDS}
          fetcher={fetcher}
        />
        <EtlPanel
          title="WoodMac"
          description="Fetch WoodMac query results and post them to Stitch."
          baseUrl={config.etlWoodmacBaseUrl}
          fields={WOODMAC_FIELDS}
          fetcher={fetcher}
        />
      </div>
    </div>
  );
}
