import { useQueries } from "@tanstack/react-query";
import { mergeSourceDetailsKey } from "./useMergeSourceDetails";
import { mergedResourceDetailKey } from "./useMergedResourceDetail";
import { candidateDisplayName } from "../utils/mergeCandidateName";

// The queue's display names for a list of candidates, for sorting by name.
//
// The queue items already fetch every candidate's details to show its name.
// This hook only *observes* those cache entries (its queries are disabled), so
// it makes no requests of its own; it re-renders as each entry fills in.
//
// Returns `namesById` with an entry only for candidates whose name is settled
// -- every query it depends on has succeeded or failed -- plus how many of the
// candidates that is, so the page can say when the name order is not final.
export function useCandidateDisplayNames(endpoint, candidates) {
  const list = candidates ?? [];
  const queries = list.flatMap((candidate) => [
    {
      queryKey: mergeSourceDetailsKey(endpoint, candidate.resource_ids),
      enabled: false,
    },
    ...(candidate.merged_resource_id
      ? [
          {
            queryKey: mergedResourceDetailKey(
              endpoint,
              candidate.merged_resource_id,
            ),
            enabled: false,
          },
        ]
      : []),
  ]);

  return useQueries({
    queries,
    combine: (results) => {
      const namesById = new Map();
      let index = 0;
      for (const candidate of list) {
        const source = results[index++];
        const merged = candidate.merged_resource_id ? results[index++] : null;
        const settled =
          source.status !== "pending" &&
          (!merged || merged.status !== "pending");
        if (settled) {
          namesById.set(
            candidate.id,
            candidateDisplayName(candidate.id, {
              sourceDetails: source.data,
              mergedResource: merged?.data,
            }),
          );
        }
      }
      return { namesById, loadedCount: namesById.size, total: list.length };
    },
  });
}
