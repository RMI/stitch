import { useEffect, useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import Card from "../components/Card";
import Button from "../components/Button";
import Input from "../components/Input";
import ResourceView from "../components/ResourceView";
import {
  useMergeCandidates,
  useMergeCandidate,
  useMergeCandidatePreview,
} from "../hooks/useResources";
import { createAuthenticatedFetcher } from "../auth/api";
import { reviewMergeCandidate } from "../queries/api";
import { resourceKeys } from "../queries/resources";
import JsonView from "../components/JsonView";

const ENDPOINT = "oil-gas-fields";

function SummaryRow({ candidate, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(candidate.id)}
      className={`w-full text-left border rounded-lg px-4 py-3 transition ${
        isSelected
          ? "border-blue-600 bg-blue-50"
          : "border-gray-200 bg-white hover:bg-gray-50"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold">Candidate #{candidate.id}</div>
        <div className="text-sm text-gray-600">{candidate.status}</div>
      </div>
      <div className="text-sm mt-2 text-gray-700">
        Resources: {candidate.resource_ids.join(", ")}
      </div>
      {candidate.merged_resource_id ? (
        <div className="text-sm mt-1 text-gray-700">
          Merged resource: {candidate.merged_resource_id}
        </div>
      ) : null}
    </button>
  );
}

export default function MergeCandidateReviewPage() {
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();
  const fetcher = useMemo(
    () => createAuthenticatedFetcher(getAccessTokenSilently),
    [getAccessTokenSilently],
  );

  const [selectedId, setSelectedId] = useState(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [actionError, setActionError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const {
    data: candidates,
    isLoading: listLoading,
    isError: listError,
    error: listErrorObj,
    refetch: refetchCandidates,
  } = useMergeCandidates(ENDPOINT, true);

  useEffect(() => {
    refetchCandidates();
  }, [refetchCandidates]);

  useEffect(() => {
    if (!selectedId && candidates?.length) {
      const firstPending = candidates.find((c) => c.status === "PENDING");
      setSelectedId(firstPending?.id ?? candidates[0].id);
    }
  }, [candidates, selectedId]);

  const {
    data: candidate,
    isLoading: candidateLoading,
    isError: candidateError,
    error: candidateErrorObj,
    refetch: refetchCandidate,
  } = useMergeCandidate(ENDPOINT, selectedId, Boolean(selectedId));

  useEffect(() => {
    if (selectedId) {
      refetchCandidate();
    }
  }, [selectedId, refetchCandidate]);

  const shouldShowPreview = candidate?.status === "PENDING";

  const {
    data: preview,
    isLoading: previewLoading,
    isError: previewError,
    error: previewErrorObj,
    refetch: refetchPreview,
  } = useMergeCandidatePreview(
    ENDPOINT,
    selectedId,
    Boolean(selectedId) && shouldShowPreview,
  );

  useEffect(() => {
    if (selectedId && shouldShowPreview) {
      refetchPreview();
    }
  }, [selectedId, shouldShowPreview, refetchPreview]);

  const pendingCount =
    candidates?.filter((c) => c.status === "PENDING").length ?? 0;

  async function handleReview(action) {
    if (!candidate?.id) return;

    setActionLoading(true);
    setActionError(null);

    try {
      await reviewMergeCandidate(
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
          queryKey: resourceKeys.mergeCandidatePreview(ENDPOINT, candidate.id),
        }),
      ]);

      refetchCandidates();
      refetchCandidate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Merge Candidate Review</h1>
        <p className="text-gray-700 mt-2">
          Review pending merge candidates, inspect the constituent resources,
          and approve or deny the merge.
        </p>
      </div>

      <Card title="Summary">
        <div className="grid gap-2 text-sm">
          <div>Total candidates: {candidates?.length ?? 0}</div>
          <div>Pending: {pendingCount}</div>
          <div>
            Approved:{" "}
            {candidates?.filter((c) => c.status === "APPROVED").length ?? 0}
          </div>
          <div>
            Denied:{" "}
            {candidates?.filter((c) => c.status === "DENIED").length ?? 0}
          </div>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <Card title="Candidates">
          {listLoading ? (
            <p>Loading…</p>
          ) : listError ? (
            <pre className="text-sm text-red-700 whitespace-pre-wrap">
              {listErrorObj?.message ?? "Failed to load merge candidates."}
            </pre>
          ) : candidates?.length ? (
            <div className="space-y-3">
              {candidates.map((item) => (
                <SummaryRow
                  key={item.id}
                  candidate={item}
                  isSelected={item.id === selectedId}
                  onSelect={(id) => {
                    setSelectedId(id);
                    setReviewNotes("");
                    setActionError(null);
                  }}
                />
              ))}
            </div>
          ) : (
            <p>No merge candidates found.</p>
          )}
        </Card>

        <div className="space-y-6">
          <Card
            title={selectedId ? `Candidate #${selectedId}` : "Candidate detail"}
          >
            {!selectedId ? (
              <p>Select a candidate.</p>
            ) : candidateLoading ? (
              <p>Loading…</p>
            ) : candidateError ? (
              <pre className="text-sm text-red-700 whitespace-pre-wrap">
                {candidateErrorObj?.message ?? "Failed to load candidate."}
              </pre>
            ) : candidate ? (
              <div className="space-y-4">
                {shouldShowPreview ? (
                  previewLoading ? (
                    <p>Loading preview…</p>
                  ) : previewError ? (
                    <pre className="text-sm text-red-700 whitespace-pre-wrap">
                      {previewErrorObj?.message ?? "Failed to load preview."}
                    </pre>
                  ) : preview?.data ? (
                    <div className="space-y-3">
                      <div className="text-sm text-gray-700">
                        This is the merged result that will be created if
                        approved.
                      </div>
                      <div className="text-sm text-gray-600">
                        Merging resources: {preview.resource_ids.join(", ")}
                      </div>

                      <JsonView
                        data={preview.data}
                        isLoading={false}
                        isError={false}
                        error={null}
                        message="No preview available."
                      />
                    </div>
                  ) : (
                    <p>No preview available.</p>
                  )
                ) : (
                  <div className="space-y-2 text-sm text-gray-600">
                    <p>Preview is only available for pending candidates.</p>
                    {candidate.merged_resource_id ? (
                      <p>
                        This candidate was already approved and produced merged
                        resource {candidate.merged_resource_id}.
                      </p>
                    ) : null}
                  </div>
                )}

                <div className="grid gap-1 text-sm">
                  <div>Status: {candidate.status}</div>
                  <div>Resources: {candidate.resource_ids.join(", ")}</div>
                  {candidate.review_notes ? (
                    <div>Existing notes: {candidate.review_notes}</div>
                  ) : null}
                  {candidate.merged_resource_id ? (
                    <div>
                      Merged resource ID: {candidate.merged_resource_id}
                    </div>
                  ) : null}
                </div>

                <label className="block">
                  <div className="text-sm font-medium mb-2">Review notes</div>
                  <Input
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    className="w-full"
                    placeholder="Optional review notes"
                  />
                </label>

                {candidate.status === "PENDING" ? (
                  <div className="flex gap-3">
                    <Button
                      onClick={() => handleReview("approve")}
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Working..." : "Approve"}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleReview("deny")}
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Working..." : "Deny"}
                    </Button>
                  </div>
                ) : (
                  <div className="text-sm text-gray-600">
                    This candidate has already been reviewed.
                  </div>
                )}

                {actionError ? (
                  <pre className="text-sm text-red-700 whitespace-pre-wrap">
                    {actionError}
                  </pre>
                ) : null}
              </div>
            ) : (
              <p>No candidate loaded.</p>
            )}
          </Card>

          {candidate?.resource_ids?.length ? (
            <div className="grid gap-6 xl:grid-cols-2">
              {candidate.resource_ids.map((resourceId) => (
                <Card key={resourceId} title={`Resource ${resourceId}`}>
                  <ResourceView
                    endpoint={ENDPOINT}
                    initialID={resourceId}
                    showControls={false}
                  />
                </Card>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
