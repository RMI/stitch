import { useConfig } from "../config/useConfig";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { getResourceDetail } from "../queries/api";

// The cache key for a candidate's source details.
function mergeSourceDetailsKey(endpoint, resourceIds) {
  return [endpoint, "merge-source-details", ...(resourceIds ?? [])];
}

// Fetches every source resource in a merge candidate as one aggregate query, so
// all entries arrive (and error) together. Used for the selected candidate's
// per-column source mix in the review panel.
export function useMergeSourceDetails(endpoint, resourceIds, enabled = true) {
  const config = useConfig();
  const ids = resourceIds ?? [];

  return useAuthenticatedQuery({
    queryKey: mergeSourceDetailsKey(endpoint, ids),
    queryFn: (fetcher) =>
      Promise.all(
        ids.map((id) => getResourceDetail(config, id, fetcher, endpoint)),
      ),
    enabled: enabled && ids.length > 0,
  });
}
