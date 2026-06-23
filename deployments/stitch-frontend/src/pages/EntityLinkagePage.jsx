import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import { createAuthenticatedFetcher } from "../auth/api";
import { useJobRunner } from "../hooks/useJobRunner";
import JobTriggerButton from "../components/JobTriggerButton";
import JobResultList from "../components/JobResultList";
import LastUpdated from "../components/LastUpdated";
import StructuredDataView from "../components/StructuredDataView";

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
  const fetcher = createAuthenticatedFetcher(config, getAccessTokenSilently);

  const [applyMerges, setApplyMerges] = useState(false);
  const [forceRerun, setForceRerun] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const job = useJobRunner({
    baseUrl: config.entityLinkageBaseUrl,
    fetcher,
    paramsKey: `${applyMerges}`,
    matchesParams: (record) => record.params?.apply_merges === applyMerges,
  });

  function handleToggleApplyMerges(event) {
    setApplyMerges(event.target.checked);
    setForceRerun(false);
    setRevealed(false);
  }

  async function handleTrigger() {
    // A recent run with these params exists and we're not forcing → reveal it.
    if (job.hasExisting && !forceRerun && !revealed) {
      setRevealed(true);
      return;
    }
    setRevealed(true);
    await job.start({ apply_merges: applyMerges, force: forceRerun });
    setForceRerun(false);
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">Entity Linkage</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an entity-linkage run and review the result. A run already in
          progress (or recently completed) for the same options is shared rather
          than started again.
        </p>
      </div>

      <div className="mb-6 space-y-4 rounded-md border border-line bg-panel p-4">
        <label className="flex items-center gap-3 text-sm font-medium text-ink">
          <input
            type="checkbox"
            checked={applyMerges}
            onChange={handleToggleApplyMerges}
            disabled={job.isRunning}
            className="accent-primary"
          />
          <span>Initiate merges</span>
        </label>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
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
                onChange={(event) => setForceRerun(event.target.checked)}
                disabled={job.isRunning}
                className="accent-primary"
              />
              <span>Re-run (ignore a recent run)</span>
            </label>
          </div>
          <LastUpdated at={job.lastUpdatedAt} />
        </div>
      </div>

      {job.error && (
        <div className="mb-6 rounded-md border border-danger/25 bg-danger-soft p-4 text-sm text-danger">
          {job.error}
        </div>
      )}

      {revealed && (
        <section>
          <h2 className="mb-2 text-lg font-semibold text-ink">Runs</h2>
          <JobResultList
            records={job.records}
            renderResult={(record) =>
              record.state === "succeeded" ? (
                <RunResult result={record.result} />
              ) : record.state === "failed" ? (
                <p className="text-sm text-danger">
                  {record.error || "Run failed."}
                </p>
              ) : (
                <p className="text-sm text-ink-muted">Running…</p>
              )
            }
          />
        </section>
      )}
    </div>
  );
}
