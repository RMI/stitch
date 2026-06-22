import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";

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

function formatCount(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function getMatchGroups(result) {
  return Array.isArray(result?.match_groups) ? result.match_groups : [];
}

function getResultDetails(result) {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    return result;
  }

  const { match_groups: _matchGroups, ...details } = result;
  return details;
}

function MatchGroupsSummary({ groups }) {
  if (!groups.length) {
    return <p className="text-sm text-ink-muted">No match groups found.</p>;
  }

  return (
    <ol className="space-y-3">
      {groups.map((group, index) => {
        const resourceIds = Array.isArray(group) ? group : [];

        return (
          <li
            key={`${index}-${resourceIds.join("-")}`}
            className="rounded-md border border-line bg-panel p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
              <h4 className="text-sm font-semibold text-ink">
                Match group {index + 1}
              </h4>
              <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold text-ink-muted">
                {formatCount(resourceIds.length, "resource")}
              </span>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {resourceIds.map((id) => (
                <span
                  key={id}
                  className="rounded-md border border-line bg-surface px-2.5 py-1 text-sm font-medium text-ink"
                >
                  Resource {id}
                </span>
              ))}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function RunResult({ result }) {
  const matchGroups = getMatchGroups(result);
  const details = getResultDetails(result);

  return (
    <div className="space-y-5">
      <section>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-ink">Match groups</h3>
          <span className="text-sm font-medium text-ink-muted">
            {formatCount(matchGroups.length, "group")}
          </span>
        </div>

        <div className="mt-3">
          <MatchGroupsSummary groups={matchGroups} />
        </div>
      </section>

      <section className="border-t border-line pt-4">
        <h3 className="mb-3 text-base font-semibold text-ink">Run details</h3>
        <StructuredDataView data={details} label="Entity linkage run details" />
      </section>
    </div>
  );
}

export default function EntityLinkagePage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();

  const [applyMerges, setApplyMerges] = useState(false);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);

  async function handleStart() {
    setStarting(true);
    setError(null);

    try {
      const token = await getAccessTokenSilently({
        authorizationParams: { audience: config.auth0.audience },
      });

      const response = await fetch(`${config.entityLinkageBaseUrl}/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          apply_merges: applyMerges,
        }),
      });

      const parsed = await parseJsonResponse(response);

      if (!response.ok) {
        setError({ status: response.status, body: parsed });
        return;
      }

      // 202 starts a new run; 200 means an identical run is already active or
      // recently finished — either way `parsed` is the job record to track.
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
    const jobId = record?.job_id;
    if (!jobId) return;

    setRefreshing(true);
    setError(null);

    try {
      // GET /status/{job_id} is unauthenticated, like the other job services.
      const response = await fetch(
        `${config.entityLinkageBaseUrl}/status/${jobId}`,
      );
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

  const state = record?.state;
  const isRunning = state === "running";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">Entity Linkage</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an entity-linkage run, then refresh to check its status and
          review the result. An identical run already in progress is shared
          rather than started again.
        </p>
      </div>

      <div className="mb-6 rounded-md border border-line bg-panel p-4">
        <label className="flex items-center gap-3 text-sm font-medium text-ink">
          <input
            type="checkbox"
            checked={applyMerges}
            onChange={(e) => setApplyMerges(e.target.checked)}
            disabled={isRunning}
            className="accent-primary"
          />
          <span>Initiate merges</span>
        </label>

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
            disabled={refreshing || !record}
            variant="secondary"
          >
            {refreshing ? "Refreshing…" : "Refresh status"}
          </Button>
        </div>
      </div>

      {error ? (
        <section className="mb-6">
          <h2 className="mb-2 text-lg font-semibold text-ink">Run error</h2>
          <div className="rounded-md border border-danger/25 bg-danger-soft p-4 text-sm text-danger">
            <StructuredDataView data={error} label="Entity linkage error" />
          </div>
        </section>
      ) : null}

      <section>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">Run status</h2>
          <StateBadge state={state} />
        </div>
        <div className="rounded-md border border-line bg-panel p-4">
          {!record ? (
            <p className="text-sm text-ink-muted">
              No run started yet. Start a run to begin.
            </p>
          ) : isRunning ? (
            <p className="text-sm text-ink-muted">
              Run in progress — refresh to check for the result.
            </p>
          ) : state === "failed" ? (
            <div className="space-y-2">
              <p className="text-sm font-medium text-danger">Run failed.</p>
              <StructuredDataView
                data={record.error ?? record}
                label="Entity linkage failure"
              />
            </div>
          ) : (
            <RunResult result={record.result} />
          )}
        </div>
      </section>
    </div>
  );
}
