import { useCallback, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";

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

function RunResult({ result }) {
  if (!result) {
    return (
      <p className="text-sm text-ink-muted">
        No run started yet. Start a run to begin.
      </p>
    );
  }

  return (
    <div className="space-y-5">
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
        <h3 className="mb-3 text-base font-semibold text-ink">Run details</h3>
        <StructuredDataView
          data={getResultDetails(result)}
          label="Entity linkage run details"
        />
      </section>
    </div>
  );
}

export default function EntityLinkagePage() {
  useDocumentTitle("Entity linkage");
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const baseUrl = config.apiBaseUrl;

  const [applyMerges, setApplyMerges] = useState(false);
  const [starting, setStarting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const getToken = useCallback(
    () =>
      getAccessTokenSilently({
        authorizationParams: { audience: config.auth0.audience },
      }),
    [getAccessTokenSilently, config.auth0.audience],
  );

  async function handleStart() {
    setStarting(true);
    setError(null);

    try {
      const token = await getToken();

      // apply_merges is a query parameter on this route, not a body field.
      const response = await fetch(
        `${baseUrl}/oil-gas-fields/merge-candidates/link-all?apply_merges=${applyMerges}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );

      const parsed = await parseJsonResponse(response);

      if (!response.ok) {
        setError({ status: response.status, body: parsed });
        return;
      }

      setResult(parsed);
    } catch (err) {
      setError({
        status: null,
        body: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Entity linkage
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          Find groups of resources that look like duplicates of each other. With
          &ldquo;Initiate merges&rdquo; checked, each group is also queued for
          human review on the Merge review page.
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
          <Button onClick={handleStart} disabled={starting} variant="primary">
            {starting ? "Starting…" : "Start run"}
          </Button>
        </div>
      </div>

      {error ? (
        <section className="mb-6">
          <h2 className="mb-2 text-lg font-semibold text-ink">Run error</h2>
          <div className="rounded-md border border-danger/25 bg-danger-soft p-4 text-sm text-danger">
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
          <RunResult result={result} />
        </div>
      </section>
    </div>
  );
}
