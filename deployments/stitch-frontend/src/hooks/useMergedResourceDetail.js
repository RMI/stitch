import { useConfig } from "../config/useConfig";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { getResourceDetail } from "../queries/api";

// The cache key for a merged resource's detail. Exported so the queue's sort
// (useCandidateDisplayNames) can read the same cache entry without fetching.
export function mergedResourceDetailKey(endpoint, resourceId) {
  return [endpoint, "merged-resource-detail", resourceId];
}

// Fetches the resource a merge produced. Callers share a cache entry keyed by
// endpoint + resource id, so the merged resource view and the review panel
// heading don't issue duplicate requests. Disabled until a resource id exists
// (i.e. the candidate has actually been merged).
export function useMergedResourceDetail(endpoint, resourceId) {
  const config = useConfig();

  return useAuthenticatedQuery({
    queryKey: mergedResourceDetailKey(endpoint, resourceId),
    queryFn: (fetcher) =>
      getResourceDetail(config, resourceId, fetcher, endpoint),
    enabled: Boolean(resourceId),
  });
}
