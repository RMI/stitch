import { SOURCE_PRIORITY } from "../constants/sourceMeta";
import { isEmptyValue } from "./mergeComparison";

function sourceRank(source) {
  const index = SOURCE_PRIORITY.indexOf(source);
  return index === -1 ? SOURCE_PRIORITY.length : index;
}

// Picks a display name for a merge candidate from its source resources' detail
// views, using the same source-priority rules as backend coalescing: the
// name from the best-ranked source wins, ties broken by resource order.
export function pickCandidateName(details) {
  let winner = null;

  for (const detail of details) {
    const name = detail?.data?.name;
    if (isEmptyValue(name)) continue;

    const rank = sourceRank(detail?.provenance?.name);
    if (!winner || rank < winner.rank) {
      winner = { name, rank };
    }
  }

  return winner?.name ?? null;
}

// The name the Merge Review queue shows for a candidate. Post-merge the source
// resources are null shells, so the merged resource's name wins; otherwise the
// source-priority pick above; otherwise the candidate id. Shared by the queue
// items and the queue's name sort, so the two can never disagree.
export function candidateDisplayName(
  candidateId,
  { sourceDetails, mergedResource },
) {
  const mergedName = isEmptyValue(mergedResource?.data?.name)
    ? null
    : mergedResource.data.name;
  const sourceName = sourceDetails ? pickCandidateName(sourceDetails) : null;
  return mergedName ?? sourceName ?? `Candidate #${candidateId}`;
}
