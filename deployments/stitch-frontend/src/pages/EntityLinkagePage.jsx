import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
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

  if (!result) {
    return <p className="text-sm text-ink-muted">No run has completed yet.</p>;
  }

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
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleStart() {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const token = await getAccessTokenSilently();

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

      const text = await response.text();

      let parsed;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        parsed = { raw: text };
      }

      if (!response.ok) {
        setError({
          status: response.status,
          body: parsed,
        });
        return;
      }

      setResult(parsed);
    } catch (err) {
      setError({
        status: null,
        body: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">Entity Linkage</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an entity-linkage run and review the result.
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

        <div className="mt-4">
          <Button onClick={handleStart} disabled={loading} variant="primary">
            {loading ? "Running…" : "Start run"}
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
        <h2 className="mb-2 text-lg font-semibold text-ink">Run result</h2>
        <div className="rounded-md border border-line bg-panel p-4">
          <RunResult result={result} />
        </div>
      </section>
    </div>
  );
}
