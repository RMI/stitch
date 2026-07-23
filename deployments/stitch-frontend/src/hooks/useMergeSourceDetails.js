import { useConfig } from "../config/useConfig";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { getResourceDetail } from "../queries/api";

// Fetches every source resource in a merge candidate as one aggregate query, so
// all entries arrive (and error) together. Callers share a cache entry keyed by
// endpoint + resource ids, so the source comparison table and the candidate
// name lookup don't issue duplicate requests for the same candidate.
export function useMergeSourceDetails(endpoint, resourceIds, enabled = true) {
  const config = useConfig();
  const ids = resourceIds ?? [];

  return useAuthenticatedQuery({
    queryKey: [endpoint, "merge-source-details", ...ids],
    queryFn: (fetcher) =>
      Promise.all(
        ids.map((id) => getResourceDetail(config, id, fetcher, endpoint)),
      ),
    enabled: enabled && ids.length > 0,
  });
}
