import { useCallback, useEffect, useRef, useState } from "react";
import { findJobs, getJobStatus, startJob } from "../queries/jobs";

const POLL_INTERVAL_MS = 1000;

function sortNewestFirst(records) {
  return [...records].sort(
    (a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );
}

// Drives a Stitch job from the UI: loads the prior runs for the current params
// on mount, starts/auto-polls runs, and tracks the records (newest first).
// Shared by every job-shaped service (LLM, entity-linkage, ETL).
//
// - baseUrl: where the job routes live (POST /start, POST /find, GET /status).
// - fetcher: authenticated fetch wrapper (may change each render — captured by ref).
// - lookupBody: the request params (without `force`) used to look up existing
//   runs via /find; the server filters by the same dedup policy as /start, so
//   there's no fetch-everything-then-filter and no client/server filter drift.
export function useJobRunner({ baseUrl, fetcher, lookupBody }) {
  const [records, setRecords] = useState([]);
  const [isStarting, setIsStarting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);

  // Stable refs so the load effect doesn't churn on every parent re-render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const lookupRef = useRef(lookupBody);
  lookupRef.current = lookupBody;
  // Serialized lookup params double as the effect's reload key.
  const lookupKey = JSON.stringify(lookupBody ?? null);
  // Bumped whenever params change / on unmount, to cancel stale polls.
  const generationRef = useRef(0);

  const upsert = useCallback((record) => {
    setRecords((prev) =>
      sortNewestFirst([
        ...prev.filter((r) => r.job_id !== record.job_id),
        record,
      ]),
    );
    setLastUpdatedAt(Date.now());
  }, []);

  const poll = useCallback(
    async (jobId, generation) => {
      setIsPolling(true);
      try {
        while (generationRef.current === generation) {
          const record = await getJobStatus(baseUrl, jobId, fetcherRef.current);
          if (generationRef.current !== generation) return;
          upsert(record);
          if (record.state !== "running") return;
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        }
      } catch (err) {
        if (generationRef.current === generation) {
          setError(err.message || "Failed to check job status.");
        }
      } finally {
        if (generationRef.current === generation) setIsPolling(false);
      }
    },
    [baseUrl, upsert],
  );

  // Load the runs for the current params on mount / when params change.
  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    setRecords([]);
    setError("");
    setIsPolling(false);

    (async () => {
      try {
        const mine = await findJobs(
          baseUrl,
          lookupRef.current ?? {},
          fetcherRef.current,
        );
        if (generationRef.current !== generation) return;
        const sorted = sortNewestFirst(mine);
        setRecords(sorted);
        setLastUpdatedAt(Date.now());
        const running = sorted.find((r) => r.state === "running");
        if (running) poll(running.job_id, generation);
      } catch {
        // No prior runs (or lookup unavailable) — start from a clean slate.
        if (generationRef.current === generation) setRecords([]);
      }
    })();

    return () => {
      generationRef.current += 1; // cancel any in-flight poll for this generation
    };
  }, [baseUrl, lookupKey, poll]);

  const start = useCallback(
    async (body) => {
      setIsStarting(true);
      setError("");
      const generation = generationRef.current;
      try {
        const record = await startJob(baseUrl, body, fetcherRef.current);
        if (generationRef.current !== generation) return record;
        upsert(record);
        if (record.state === "running") poll(record.job_id, generation);
        return record;
      } catch (err) {
        setError(err.message || "Failed to start job.");
        return null;
      } finally {
        setIsStarting(false);
      }
    },
    [baseUrl, poll, upsert],
  );

  // Known behavior: `current` is the newest run by start time (which drives the
  // running/spinner state), while `latestSucceeded` (used for results/persist)
  // is the newest succeeded run. With force re-runs these can differ briefly.
  const current = records[0] ?? null;
  const latestSucceeded = records.find((r) => r.state === "succeeded") ?? null;

  return {
    records,
    current,
    latestSucceeded,
    hasExisting: records.length > 0,
    isRunning: isStarting || isPolling || current?.state === "running",
    isStarting,
    isPolling,
    error,
    lastUpdatedAt,
    start,
  };
}
