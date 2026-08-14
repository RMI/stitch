import { useCallback, useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";
import StateBadge from "../components/StateBadge";

// While a run is active the status endpoint is polled on this cadence so the
// page reflects progress without the user clicking "Refresh status".
const POLL_INTERVAL_MS = 2000;

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

async function parseJsonResponse(response) {
  const text = await response.text();

  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return { raw: text };
  }
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

function RunResult({ record }) {
  if (!record) {
    return (
      <p className="text-sm text-ink-muted">
        No run started yet. Start a run to begin.
      </p>
    );
  }

  const result = record.result;

  return (
    <div className="space-y-5">
      {result ? (
        <>
          <section>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-base font-semibold text-ink">Match groups</h3>
              <span className="text-sm font-medium text-ink-muted">
                {formatCount(getMatchGroups(result).length, "group")}
              </span>
            </div>

            <div className="mt-3">
              <MatchGroupsSummary groups={getMatchGroups(result)} />
            </div>
          </section>

          <section className="border-t border-line pt-4">
            <h3 className="mb-3 text-base font-semibold text-ink">
              Run details
            </h3>
            <StructuredDataView
              data={getResultDetails(result)}
              label="Entity linkage run details"
            />
          </section>
        </>
      ) : record.state === "running" ? (
        <p className="text-sm text-ink-muted">
          {record.progress
            ? `Run in progress — ${record.progress.resources_scanned.toLocaleString()} resources checked so far, ${record.progress.match_groups_found.toLocaleString()} duplicate groups found. Status refreshes automatically.`
            : "Run in progress — status refreshes automatically."}
        </p>
      ) : record.state === "failed" ? (
        <div className="rounded-md border border-danger/25 bg-danger-soft p-3 text-sm text-danger">
          {record.error || "Run failed."}
        </div>
      ) : (
        <p className="text-sm text-ink-muted">No result available.</p>
      )}

      <section className="border-t border-line pt-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">Job status</h3>
        <StructuredDataView data={record} label="Entity linkage job status" />
      </section>
    </div>
  );
}

export default function EntityLinkagePage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const baseUrl = config.entityLinkageBaseUrl;

  const [applyMerges, setApplyMerges] = useState(false);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);

  const getToken = useCallback(
    () =>
      getAccessTokenSilently({
        authorizationParams: { audience: config.auth0.audience },
      }),
    [getAccessTokenSilently, config.auth0.audience],
  );

  // Status is permission-gated (unlike the ETL service's open /status), so the
  // bearer token is sent on the poll as well as the start.
  const fetchStatus = useCallback(
    async ({ manual = false } = {}) => {
      if (manual) {
        setRefreshing(true);
        setError(null);
      }

      try {
        const token = await getToken();
        const response = await fetch(`${baseUrl}/oil-gas-fields/link/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const parsed = await parseJsonResponse(response);

        if (response.status === 404) {
          setRecord(null);
          if (manual) {
            setError({
              status: 404,
              message: "No linkage run has been started yet.",
              body: parsed,
            });
          }
          return;
        }

        if (!response.ok) {
          if (manual) setError({ status: response.status, body: parsed });
          return;
        }

        setRecord(parsed);
      } catch (err) {
        if (manual) {
          setError({
            status: null,
            body: err instanceof Error ? err.message : String(err),
          });
        }
      } finally {
        if (manual) setRefreshing(false);
      }
    },
    [baseUrl, getToken],
  );

  // Auto-poll while a run is active; stop once it reaches a terminal state.
  useEffect(() => {
    if (record?.state !== "running") return undefined;

    const id = setInterval(() => {
      fetchStatus();
    }, POLL_INTERVAL_MS);

    return () => clearInterval(id);
  }, [record?.state, fetchStatus]);

  async function handleStart() {
    setStarting(true);
    setError(null);

    try {
      const token = await getToken();

      const response = await fetch(`${baseUrl}/oil-gas-fields/link`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ apply_merges: applyMerges }),
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

  const isRunning = record?.state === "running";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-3xl font-semibold text-ink">Entity Linkage</h1>
          <StateBadge state={record?.state} />
        </div>
        <p className="mt-2 text-sm text-ink-muted">
          Start an entity-linkage run and review the result. The run happens in
          the background — only one run may be active at a time.
        </p>
      </div>

      <div className="mb-6 rounded-md border border-line bg-panel p-4">
        <label className="flex items-center gap-3 text-sm font-medium text-ink">
          <input
            type="checkbox"
            checked={applyMerges}
            onChange={(e) => setApplyMerges(e.target.checked)}
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
            onClick={() => fetchStatus({ manual: true })}
            disabled={refreshing}
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
            {error.message ? (
              <p className="mb-2 font-medium">{error.message}</p>
            ) : null}
            <StructuredDataView
              data={{ status: error.status, response: error.body }}
              label="Entity linkage error"
            />
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="mb-2 text-lg font-semibold text-ink">Run result</h2>
        <div className="rounded-md border border-line bg-panel p-4">
          <RunResult record={record} />
        </div>
      </section>
    </div>
  );
}
