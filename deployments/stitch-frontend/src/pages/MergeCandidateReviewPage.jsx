import { useState } from "react";
import { Link } from "react-router";
import Button from "../components/Button";
import MergeSourceComparison from "../components/MergeSourceComparison";
import MergedResourceView from "../components/MergedResourceView";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useMergeCandidateName } from "../hooks/useMergeCandidateName";
import { useMergedResourceDetail } from "../hooks/useMergedResourceDetail";
import {
  useMergeCandidates,
  useMergeCandidate,
  useReviewMergeCandidate,
} from "../hooks/useResources";
import { pickCompareName } from "../utils/candidateCompare";
import { isEmptyValue } from "../utils/mergeComparison";
import { readCandidateStaleness } from "../utils/mergeCandidateStaleness";

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

// PENDING reads as "CANDIDATE": it isn't a real merged resource yet.
function getStatusLabel(status) {
  return status === "PENDING" ? "CANDIDATE" : status;
}

function StatusBadge({ status }) {
  return (
    <span
      className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold ${getStatusClasses(status)}`}
    >
      {getStatusLabel(status)}
    </span>
  );
}

// Resource and merged ids aren't shown as list text, but stay one hover away
// via the title attribute (and remain visible in the detail view facts).
function candidateSourcesTitle(candidate) {
  const parts = [`Source resources: ${candidate.resource_ids.join(", ")}`];
  if (candidate.merged_resource_id) {
    parts.push(`Merged resource: ${candidate.merged_resource_id}`);
  }
  return parts.join(" · ");
}

function CandidateQueueItem({ candidate, isSelected, onSelect }) {
  const sourceName = useMergeCandidateName(ENDPOINT, candidate.resource_ids);
  // Post-merge, the source resources are null shells, so the merged resource
  // is the authoritative name source. The hook is disabled until an id exists,
  // so pending candidates skip the fetch.
  const { data: mergedResource } = useMergedResourceDetail(
    ENDPOINT,
    candidate.merged_resource_id,
  );
  const mergedName = isEmptyValue(mergedResource?.data?.name)
    ? null
    : mergedResource.data.name;
  const displayName = mergedName ?? sourceName ?? `Candidate #${candidate.id}`;

  return (
    <button
      type="button"
      onClick={() => onSelect(candidate.id)}
      aria-pressed={isSelected}
      title={candidateSourcesTitle(candidate)}
      className={`w-full rounded-md border px-3 py-3 text-left transition ${
        isSelected
          ? "border-primary bg-primary-soft"
          : "border-transparent bg-panel hover:border-line hover:bg-surface"
      } focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2`}
    >
      <span className="flex items-start justify-between gap-2">
        <span className="min-w-0 break-words font-semibold text-ink">
          {displayName}
        </span>
        <StatusBadge status={candidate.status} />
      </span>
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
  const { moves } = readCandidateStaleness(candidate);
  const movedTo = new Map(moves.map((m) => [m.resource_id, m.repointed_to]));
  // Once approved, the source resources are null shells whose links only
  // redirect to the merged resource, so show them as plain text. A candidate
  // that hasn't been merged still links to its live source resources.
  const isApproved = candidate.status === "APPROVED";
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-3">
      <div>
        <dt className="font-semibold text-ink-muted">Status</dt>
        <dd className="mt-1 text-ink">{candidate.status}</dd>
      </div>
      <div>
        <dt className="font-semibold text-ink-muted">Source resources</dt>
        <dd className="mt-1 break-words text-ink">
          {candidate.resource_ids.map((id, index) => (
            <span key={id}>
              {index > 0 ? ", " : null}
              {isApproved ? (
                id
              ) : (
                <Link
                  to={`/${ENDPOINT}/${id}`}
                  className="text-primary underline"
                >
                  {id}
                </Link>
              )}
              {movedTo.has(id) ? (
                <span className="text-ink-muted">
                  {" "}
                  (now{" "}
                  <Link
                    to={`/${ENDPOINT}/${movedTo.get(id)}`}
                    className="text-primary underline"
                  >
                    {movedTo.get(id)}
                  </Link>
                  )
                </span>
              ) : null}
            </span>
          ))}
        </dd>
      </div>
      <div>
        <dt className="font-semibold text-ink-muted">Merged resource</dt>
        <dd className="mt-1 break-words text-ink">
          {candidate.merged_resource_id ? (
            <Link
              to={`/${ENDPOINT}/${candidate.merged_resource_id}`}
              className="text-primary underline"
            >
              {candidate.merged_resource_id}
            </Link>
          ) : (
            "Not created"
          )}
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

function CandidateDecisionPanel({
  selectedId,
  listCandidate,
  candidateQuery,
  reviewNotes,
  onReviewNotesChange,
  onReview,
  actionError,
  actionLoading,
  activeReviewAction,
}) {
  const {
    data: detailCandidate,
    isLoading: candidateLoading,
    isError: candidateError,
    error: candidateErrorObj,
  } = candidateQuery;

  const candidate = detailCandidate ?? listCandidate;
  // The compare-derived name is authoritative once the detail lands. Until
  // then the queue's name stands in — it reads the same cached query the
  // queue items already issued, so no extra requests — because falling back
  // to the id would flash "Candidate #N" on first selection.
  const queueName = useMergeCandidateName(ENDPOINT, candidate?.resource_ids);
  // Post-merge, the source resources are null shells and compare carries no
  // name, so the merged resource is the authoritative source. It shares the
  // cache entry MergedResourceView fetches, so this adds no requests.
  const { data: mergedResource } = useMergedResourceDetail(
    ENDPOINT,
    candidate?.merged_resource_id,
  );
  const mergedName = isEmptyValue(mergedResource?.data?.name)
    ? null
    : mergedResource.data.name;
  const name =
    mergedName ??
    (detailCandidate ? pickCompareName(detailCandidate.compare) : queueName);

  if (!selectedId) {
    return (
      <section className="rounded-md border border-line bg-panel p-5">
        <p className="text-sm text-ink-muted">Select a candidate.</p>
      </section>
    );
  }

  // A detail error only blocks when there is nothing to show. When the queue
  // item is present it carries every field the panel renders, so the panel
  // degrades to a banner rather than disappearing.
  if (candidateError && !candidate) {
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

  // STIT-418: a member merged away since this candidate was recorded. Approving
  // would fail and Deny would record a judgment no one made, so the decision
  // controls are hidden below and this banner points at the combined record.
  const { isStale, moves } = readCandidateStaleness(candidate);

  return (
    <article className="min-w-0 overflow-hidden rounded-md border border-line bg-panel">
      {candidateError ? (
        <p className="border-b border-danger/25 bg-danger-soft px-5 py-4 text-sm text-danger">
          These details could not be refreshed and may be out of date.{" "}
          {candidateErrorObj?.message ?? "Failed to load candidate."}
        </p>
      ) : null}

      {isStale ? (
        <div className="border-b border-warning/30 bg-warning-soft px-5 py-4 text-sm text-warning">
          {moves.map((move) => (
            <p key={move.resource_id}>
              Resource{" "}
              <Link
                to={`/${ENDPOINT}/${move.resource_id}`}
                className="underline"
              >
                {move.resource_id}
              </Link>{" "}
              was merged into{" "}
              <Link
                to={`/${ENDPOINT}/${move.repointed_to}`}
                className="underline"
              >
                {move.repointed_to}
              </Link>
              .
            </p>
          ))}
          <p className="mt-2">
            This candidate is out of date and can no longer be merged. Review
            the combined record instead.
          </p>
        </div>
      ) : null}

      <div className="space-y-4 px-5 py-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="break-words text-2xl font-semibold text-ink">
              {name ?? `Candidate #${candidate.id}`}
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

      {candidate.merged_resource_id ? (
        <MergedResourceView
          endpoint={ENDPOINT}
          resourceId={candidate.merged_resource_id}
        />
      ) : (
        <MergeSourceComparison
          resourceIds={candidate.resource_ids}
          compare={detailCandidate?.compare}
          isLoading={candidateLoading}
          isError={candidateError}
          error={candidateErrorObj}
        />
      )}

      {candidate.status === "PENDING" && !isStale ? (
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
    </article>
  );
}

export default function MergeCandidateReviewPage() {
  useDocumentTitle("Merge review");
  const [selectedId, setSelectedId] = useState(null);
  const [reviewNotes, setReviewNotes] = useState("");

  const reviewMutation = useReviewMergeCandidate(ENDPOINT);
  const actionLoading = reviewMutation.isPending;
  const activeReviewAction = reviewMutation.isPending
    ? reviewMutation.variables?.action
    : null;
  const actionError = reviewMutation.error
    ? reviewMutation.error.message || String(reviewMutation.error)
    : null;

  const {
    data: candidates,
    isLoading: listLoading,
    isError: listError,
    error: listErrorObj,
  } = useMergeCandidates(ENDPOINT, true);

  // Default to the first pending candidate once the list loads. Done during
  // render (not in an effect) so the selection is set before the first paint
  // and without triggering a cascading re-render.
  if (!selectedId && candidates?.length) {
    const firstPending = candidates.find((c) => c.status === "PENDING");
    setSelectedId(firstPending?.id ?? candidates[0].id);
  }

  const candidateQuery = useMergeCandidate(
    ENDPOINT,
    selectedId,
    Boolean(selectedId),
  );
  // The detail endpoint layers `compare` on top of the list schema, so the
  // already-loaded queue item stands in for everything except the comparison
  // until the detail query lands. Without this, review actions dead-click
  // while the detail is in flight.
  const listCandidate =
    candidates?.find((item) => item.id === selectedId) ?? null;
  const candidate = candidateQuery.data ?? listCandidate;

  const pendingCount =
    candidates?.filter((c) => c.status === "PENDING").length ?? 0;
  const reviewedCount =
    candidates?.filter((c) => c.status === "APPROVED" || c.status === "DENIED")
      .length ?? 0;

  function handleSelect(id) {
    setSelectedId(id);
    setReviewNotes("");
    // Clear any error left over from reviewing the previous candidate.
    reviewMutation.reset();
  }

  function handleReview(action) {
    if (!candidate?.id) return;

    reviewMutation.mutate(
      { id: candidate.id, action, reviewNotes },
      {
        // Runs after the mutation's cache invalidation, so the queue advances
        // once the refreshed data is on its way. Failures surface via
        // `reviewMutation.error` and keep the current candidate selected.
        onSuccess: () => {
          const nextPending = candidates?.find(
            (item) => item.id !== candidate.id && item.status === "PENDING",
          );
          if (nextPending) {
            setSelectedId(nextPending.id);
          }
          setReviewNotes("");
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="border-b border-line pb-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">
              Merge review
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              Review one candidate at a time.
            </p>
          </div>
          <dl className="flex flex-wrap gap-3 text-sm">
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-xs text-ink-muted">Pending</dt>
              <dd className="font-mono text-lg font-medium tabular-nums text-ink">
                {pendingCount}
              </dd>
            </div>
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-xs text-ink-muted">Reviewed</dt>
              <dd className="font-mono text-lg font-medium tabular-nums text-ink">
                {reviewedCount}
              </dd>
            </div>
            <div className="rounded-md border border-line bg-panel px-3 py-2">
              <dt className="text-xs text-ink-muted">Total</dt>
              <dd className="font-mono text-lg font-medium tabular-nums text-ink">
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
          listCandidate={listCandidate}
          candidateQuery={candidateQuery}
          reviewNotes={reviewNotes}
          onReviewNotesChange={setReviewNotes}
          onReview={handleReview}
          actionError={actionError}
          actionLoading={actionLoading}
          activeReviewAction={activeReviewAction}
        />
      </div>
    </div>
  );
}
