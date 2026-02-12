import { getResource, getResources } from "./api";

// Query key factory - hierarchical for easy invalidation
export const resourceKeys = {
  all: ["resources"],
  lists: () => [...resourceKeys.all, "list"],
  details: () => [...resourceKeys.all, "detail"],
  detail: (id) => [...resourceKeys.details(), id],
};

export const resourceQueries = {
  list: (getAccessTokenSilently) => ({
    queryKey: resourceKeys.lists(),
    queryFn: () => getResources(getAccessTokenSilently),
  }),

  detail: (id, getAccessTokenSilently) => ({
    queryKey: resourceKeys.detail(id),
    queryFn: () => getResource(id, getAccessTokenSilently),
  }),
};
