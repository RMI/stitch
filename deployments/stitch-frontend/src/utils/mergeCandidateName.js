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
