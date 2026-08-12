/**
 * Merge candidate review states. Mirrors the backend's MergeCandidateStatus in
 * deployments/api/src/stitch/api/entities.py, which is the source of truth.
 * Keep this in sync with it until the constant is generated.
 */
export const MERGE_CANDIDATE_STATUS = {
  PENDING: "PENDING",
  APPROVED: "APPROVED",
  DENIED: "DENIED",
};

/**
 * Statuses the review queue hides unless the reviewer asks to see them. Both
 * are terminal decisions, so hiding them leaves only work that still needs a
 * human.
 *
 * This is deliberately a list of what to hide rather than what to show: a
 * status the frontend hasn't been taught about yet stays visible instead of
 * disappearing from the queue unnoticed.
 */
export const DEFAULT_HIDDEN_STATUSES = [
  MERGE_CANDIDATE_STATUS.APPROVED,
  MERGE_CANDIDATE_STATUS.DENIED,
];

export function getStatusClasses(status) {
  if (status === MERGE_CANDIDATE_STATUS.PENDING) {
    return "border-warning/30 bg-warning-soft text-warning";
  }
  if (status === MERGE_CANDIDATE_STATUS.APPROVED) {
    return "border-success/25 bg-success-soft text-success-strong";
  }
  if (status === MERGE_CANDIDATE_STATUS.DENIED) {
    return "border-danger/25 bg-danger-soft text-danger";
  }
  return "border-line bg-surface text-ink";
}

// PENDING reads as "CANDIDATE": it isn't a real merged resource yet.
export function getStatusLabel(status) {
  return status === MERGE_CANDIDATE_STATUS.PENDING ? "CANDIDATE" : status;
}
