// The name the Merge Review queue shows for a candidate: the API's
// `display_name` (the merged resource's name once approved, otherwise the
// best-ranked source's name), falling back to the candidate id. Shared by the
// queue items and the queue's name sort, so the two can never disagree.
export function candidateDisplayName(candidate) {
  return candidate.display_name || `Candidate #${candidate.id}`;
}
