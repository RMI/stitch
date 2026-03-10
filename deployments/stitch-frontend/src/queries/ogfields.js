import { getOGField, getOGFields } from "./api";

// Query key factory - hierarchical for easy invalidation
export const ogfieldKeys = {
  all: ["ogfields"],
  lists: () => [...ogfieldKeys.all, "list"],
  list: (filters) => [...ogfieldKeys.lists(), filters],
  details: () => [...ogfieldKeys.all, "detail"],
  detail: (id) => [...ogfieldKeys.details(), id],
};

// Query definitions
export const ogfieldQueries = {
  list: () => ({
    queryKey: ogfieldKeys.lists(),
    queryFn: (fetcher) => getOGFields(fetcher),
    enabled: false,
  }),

  detail: (id) => ({
    queryKey: ogfieldKeys.detail(id),
    queryFn: (fetcher) => getOGField(id, fetcher),
    enabled: false,
  }),
};
