import { useEffect, useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import ResourceView from "../components/ResourceView";
import Button from "../components/Button";
import {
  useMergeCandidates,
  useMergeCandidate,
  useMergeCandidatePreview,
} from "../hooks/useResources";
import { createAuthenticatedFetcher } from "../auth/api";
import { reviewMergeCandidate } from "../queries/api";
import { useConfig } from "../config/useConfig";
import { resourceKeys } from "../queries/resources";
import StructuredDataView from "../components/StructuredDataView";

const ENDPOINT = "oil-gas-fields";

function getStatusClasses(status) {
  if (status === "PENDING") {
    return "border-warning/30 bg-warning-soft text-warning";
  }
  if (status === "APPROVED") {
    return "border-success/25 bg-success-soft text-success-strong";
  }
  if (status === "DENIED") {
    return "border-danger/25 bg-danger-soft text-danger";
  }
  return "border-line bg-surface text-ink";
}

function StatusBadge({ status }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusClasses(status)}`}
    >
      {status}
    </span>
  );
}

function CandidateQueueItem({ candidate, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(candidate.id)}
      aria-pressed={isSelected}
      className={`w-full rounded-md border px-3 py-3 text-left transition ${
        isSelected
          ? "border-primary bg-primary-soft"
          : "border-transparent bg-panel hover:border-line hover:bg-surface"
      } focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2`}
    >
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-ink">
          Candidate #{candidate.id}
        </span>
        <StatusBadge status={candidate.status} />
      </span>
      <span className="mt-2 block break-words text-sm text-ink-muted">
        Resources {candidate.resource_ids.join(", ")}
      </span>
      {candidate.merged_resource_id ? (
        <span className="mt-1 block break-words text-sm text-ink-muted">
          Merged {candidate.merged_resource_id}
        </span>
      ) : null}
    </button>
  );
}

function QueuePanel({
  candidates,
  isLoading,
  isError,
  error,
  selectedId,
  onSelect,
}) {
  return (
    <aside className="min-w-0 rounded-md border border-line bg-panel">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-base font-semibold text-ink">Queue</h2>
      </div>

      <div className="p-2">
        {isLoading ? (
          <p className="px-2 py-3 text-sm text-ink-muted">
            Loading candidates…
          </p>
        ) : isError ? (
          <p className="px-2 py-3 text-sm text-danger">
            {error?.message ?? "Failed to load merge candidates."}
          </p>
        ) : candidates?.length ? (
          <div className="space-y-1">
            {candidates.map((item) => (
              <CandidateQueueItem
                key={item.id}
                candidate={item}
                isSelected={item.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </div>
        ) : (
          <p className="px-2 py-3 text-sm text-ink-muted">
            No merge candidates to review.
          </p>
        )}
      </div>
    </aside>
  );
}

function CandidateFacts({ candidate }) {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-3">
      <div>
        <dt className="font-semibold text-ink-muted">Status</dt>
        <dd className="mt-1 text-ink">{candidate.status}</dd>
      </div>
      <div>
        <dt className="font-semibold text-ink-muted">Source resources</dt>
        <dd className="mt-1 break-words text-ink">
          {candidate.resource_ids.join(", ")}
        </dd>
      </div>
      <div>
        <dt className="font-semibold text-ink-muted">Merged resource</dt>
        <dd className="mt-1 break-words text-ink">
          {candidate.merged_resource_id ?? "Not created"}
        </dd>
      </div>
    </dl>
  );
}

function DecisionControls({
  reviewNotes,
  onReviewNotesChange,
  onReview,
  actionLoading,
  activeReviewAction,
}) {
  return (
    <section
      aria-label="Review decision"
      className="border-t border-line bg-surface px-5 py-4"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <label
              htmlFor="decision-notes"
              className="text-sm font-semibold text-ink"
            >
              Decision notes
            </label>
            <span className="text-xs font-medium text-ink-muted">Optional</span>
          </div>
          <textarea
            id="decision-notes"
            value={reviewNotes}
            onChange={(event) => onReviewNotesChange(event.target.value)}
            rows={2}
            className="mt-2 min-h-[5.5rem] w-full rounded-md border border-line bg-panel px-3 py-2 text-sm leading-5 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            placeholder="Add rationale, uncertainty, or follow-up for the audit trail"
          />
        </div>

        <div className="flex flex-col gap-2 sm:flex-row lg:justify-end">
          <Button
            onClick={() => onReview("deny")}
            disabled={actionLoading}
            variant="danger"
            className="min-h-11"
          >
            {activeReviewAction === "deny" ? "Denying…" : "Deny merge"}
          </Button>
          <Button
            onClick={() => onReview("approve")}
            disabled={actionLoading}
            aria-describedby="decision-guidance"
            variant="confirm"
            className="min-h-11"
          >
            {activeReviewAction === "approve" ? "Approving…" : "Approve merge"}
          </Button>
        </div>
      </div>

      <p
        id="decision-guidance"
        className="mt-3 text-xs leading-5 text-ink-muted"
      >
        The decision and notes are recorded for review history.
      </p>
    </section>
  );
}

function PreviewPanel({
  candidate,
  shouldShowPreview,
  preview,
  isLoading,
  isError,
  error,
}) {
  return (
    <section className="border-t border-line px-5 py-5">
      <h3 className="text-base font-semibold text-ink">Merged preview</h3>

      <div className="mt-3">
        {shouldShowPreview ? (
          isLoading ? (
            <p className="text-sm text-ink-muted">Loading preview…</p>
          ) : isError ? (
            <p className="text-sm text-danger">
              {error?.message ?? "Failed to load preview."}
            </p>
          ) : preview?.data ? (
            <div className="space-y-3">
              <p className="text-sm text-ink-muted">
                Created from resources {preview.resource_ids.join(", ")}.
              </p>
              <div className="rounded-md border border-line bg-surface p-3">
                <StructuredDataView
                  data={preview.data}
                  label="Merged preview data"
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No preview available.</p>
          )
        ) : (
          <div className="space-y-2 text-sm text-ink-muted">
            <p>Preview is available only while a candidate is pending.</p>
            {candidate.merged_resource_id ? (
              <p>Merged resource: {candidate.merged_resource_id}</p>
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}

function SourceResources({ resourceIds, isOpen, onToggle }) {
  if (!resourceIds?.length) return null;

  return (
    <details
      open={isOpen}
      onToggle={(event) => onToggle(event.currentTarget.open)}
      className="border-t border-line px-5 py-4"
    >
      <summary className="cursor-pointer text-sm font-semibold text-ink">
        Source resources ({resourceIds.length})
      </summary>

      {isOpen ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {resourceIds.map((resourceId) => (
            <section
              key={resourceId}
              className="min-w-0 rounded-md border border-line bg-panel p-4"
            >
              <ResourceView
                endpoint={ENDPOINT}
                initialID={resourceId}
                showControls={false}
              />
            </section>
          ))}
        </div>
      ) : null}
    </details>
  );
}

function CandidateDecisionPanel({
  selectedId,
  candidateQuery,
  reviewNotes,
  onReviewNotesChange,
  onReview,
  actionError,
  actionLoading,
  activeReviewAction,
  shouldShowPreview,
  previewQuery,
  showSourceResources,
  onToggleSourceResources,
}) {
  const {
    data: candidate,
    isLoading: candidateLoading,
    isError: candidateError,
    error: candidateErrorObj,
  } = candidateQuery;
  const {
    data: preview,
    isLoading: previewLoading,
    isError: previewError,
    error: previewErrorObj,
  } = previewQuery;

  if (!selectedId) {
    return (
      <section className="rounded-md border border-line bg-panel p-5">
        <p className="text-sm text-ink-muted">Select a candidate.</p>
      </section>
    );
  }

  if (candidateLoading) {
    return (
      <section className="rounded-md border border-line bg-panel p-5">
        <p className="text-sm text-ink-muted">Loading candidate…</p>
      </section>
    );
  }

  if (candidateError) {
    return (
      <section className="rounded-md border border-line bg-panel p-5">
        <p className="text-sm text-danger">
          {candidateErrorObj?.message ?? "Failed to load candidate."}
        </p>
      </section>
    );
  }

  if (!candidate) {
    return (
      <section className="rounded-md border border-line bg-panel p-5">
        <p className="text-sm text-ink-muted">No candidate loaded.</p>
      </section>
    );
  }

  return (
    <article className="min-w-0 overflow-hidden rounded-md border border-line bg-panel">
      <div className="space-y-4 px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold text-ink">
              Candidate #{candidate.id}
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Decide whether these resources should become one curated record.
            </p>
          </div>
          <StatusBadge status={candidate.status} />
        </div>

        <CandidateFacts candidate={candidate} />

        {candidate.review_notes ? (
          <div className="rounded-md border border-line bg-surface p-3 text-sm text-ink">
            <span className="font-medium">Existing notes:</span>{" "}
            {candidate.review_notes}
          </div>
        ) : null}

        {candidate.status !== "PENDING" ? (
          <p className="rounded-md border border-line bg-surface p-3 text-sm text-ink-muted">
            This candidate has already been reviewed.
          </p>
        ) : null}
      </div>

      <PreviewPanel
        candidate={candidate}
        shouldShowPreview={shouldShowPreview}
        preview={preview}
        isLoading={previewLoading}
        isError={previewError}
        error={previewErrorObj}
      />

      {candidate.status === "PENDING" ? (
        <DecisionControls
          reviewNotes={reviewNotes}
          onReviewNotesChange={onReviewNotesChange}
          onReview={onReview}
          actionLoading={actionLoading}
          activeReviewAction={activeReviewAction}
        />
      ) : null}

      {actionError ? (
        <p className="border-t border-danger/25 bg-danger-soft px-5 py-4 text-sm text-danger">
          {actionError}
        </p>
      ) : null}

      <SourceResources
        resourceIds={candidate.resource_ids}
        isOpen={showSourceResources}
        onToggle={onToggleSourceResources}
      />
    </article>
  );
}

export default function MergeCandidateReviewPage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();
  const fetcher = useMemo(
    () => createAuthenticatedFetcher(config, getAccessTokenSilently),
    [config, getAccessTokenSilently],
  );

  const [selectedId, setSelectedId] = useState(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [actionError, setActionError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeReviewAction, setActiveReviewAction] = useState(null);
  const [showSourceResources, setShowSourceResources] = useState(false);

  const {
    data: candidates,
    isLoading: listLoading,
    isError: listError,
    error: listErrorObj,
  } = useMergeCandidates(ENDPOINT, true);

  useEffect(() => {
    if (!selectedId && candidates?.length) {
      const firstPending = candidates.find((c) => c.status === "PENDING");
      setSelectedId(firstPending?.id ?? candidates[0].id);
    }
  }, [candidates, selectedId]);

  const candidateQuery = useMergeCandidate(
    ENDPOINT,
    selectedId,
    Boolean(selectedId),
  );
  const candidate = candidateQuery.data;

  const shouldShowPreview = candidate?.status === "PENDING";

  const previewQuery = useMergeCandidatePreview(
    ENDPOINT,
    selectedId,
    Boolean(selectedId) && shouldShowPreview,
  );

  const pendingCount =
    candidates?.filter((c) => c.status === "PENDING").length ?? 0;
  const reviewedCount =
    candidates?.filter((c) => c.status === "APPROVED" || c.status === "DENIED")
      .length ?? 0;

  function handleSelect(id) {
    setSelectedId(id);
    setReviewNotes("");
    setActionError(null);
    setShowSourceResources(false);
  }

  async function handleReview(action) {
    if (!candidate?.id) return;

    setActionLoading(true);
    setActiveReviewAction(action);
    setActionError(null);

    try {
      await reviewMergeCandidate(
        config,
        candidate.id,
        action,
        fetcher,
        ENDPOINT,
        reviewNotes,
      );

      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: resourceKeys.mergeCandidates(ENDPOINT),
        }),
        queryClient.invalidateQueries({
          queryKey: resourceKeys.mergeCandidate(ENDPOINT, candidate.id),
        }),
        queryClient.invalidateQueries({
          queryKey: resourceKeys.preview(ENDPOINT, candidate.id),
        }),
      ]);

      const nextPending = candidates?.find(
        (item) => item.id !== candidate.id && item.status === "PENDING",
      );
      if (nextPending) {
        setSelectedId(nextPending.id);
      }
      setReviewNotes("");
      setShowSourceResources(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(false);
      setActiveReviewAction(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="border-b border-line pb-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Human decision queue
            </p>
            <h1 className="mt-1 text-3xl font-semibold text-ink">
              Merge Review
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              Review one candidate at a time.
            </p>
          </div>
          <dl className="flex flex-wrap gap-3 text-sm">
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-ink-muted">Pending</dt>
              <dd className="font-semibold text-ink">{pendingCount}</dd>
            </div>
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-ink-muted">Reviewed</dt>
              <dd className="font-semibold text-ink">{reviewedCount}</dd>
            </div>
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-ink-muted">Total</dt>
              <dd className="font-semibold text-ink">
                {candidates?.length ?? 0}
              </dd>
            </div>
          </dl>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <QueuePanel
          candidates={candidates}
          isLoading={listLoading}
          isError={listError}
          error={listErrorObj}
          selectedId={selectedId}
          onSelect={handleSelect}
        />

        <CandidateDecisionPanel
          selectedId={selectedId}
          candidateQuery={candidateQuery}
          reviewNotes={reviewNotes}
          onReviewNotesChange={setReviewNotes}
          onReview={handleReview}
          actionError={actionError}
          actionLoading={actionLoading}
          activeReviewAction={activeReviewAction}
          shouldShowPreview={shouldShowPreview}
          previewQuery={previewQuery}
          showSourceResources={showSourceResources}
          onToggleSourceResources={setShowSourceResources}
        />
      </div>
    </div>
  );
}
