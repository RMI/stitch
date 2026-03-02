import { getResource, getResources } from "./api";

// Query key factory - hierarchical for easy invalidation
export const resourceKeys = {
  all: ["resources"],
  lists: () => [...resourceKeys.all, "list"],
  list: (filters) => [...resourceKeys.lists(), filters],
  details: () => [...resourceKeys.all, "detail"],
  detail: (id) => [...resourceKeys.details(), id],
};

// Query definitions
export const resourceQueries = {
  list: () => ({
    queryKey: resourceKeys.lists(),
    queryFn: (fetcher) => getResources(fetcher),
    enabled: false,
  }),

  detail: (id) => ({
    queryKey: resourceKeys.detail(id),
    queryFn: (fetcher) => getResource(id, fetcher),
    enabled: false,
  }),
};
