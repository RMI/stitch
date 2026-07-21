import {
  getResourceFilterOptions,
  getResource,
  getResources,
  getResourceDetail,
  getFieldSourceValues,
  getMergeCandidates,
  getMergeCandidate,
  getMergeCandidatePreview,
} from "./api";

export const DEFAULT_STALE_TIME = 60_000;
export const DEFAULT_PAGE = 1;
export const DEFAULT_PAGE_SIZE = 10;

// Query key factory - hierarchical for easy invalidation
export const resourceKeys = {
  all: (endpoint = "resources") => [endpoint],
  lists: (endpoint = "resources") => [...resourceKeys.all(endpoint), "list"],
  list: (endpoint = "resources", filters) => [
    ...resourceKeys.lists(endpoint),
    filters,
  ],
  filterOptions: (endpoint = "resources", field) => [
    ...resourceKeys.all(endpoint),
    "filter-options",
    field,
  ],
  details: (endpoint = "resources") => [
    ...resourceKeys.all(endpoint),
    "detail",
  ],
  detail: (endpoint = "resources", id) => [
    ...resourceKeys.details(endpoint),
    id,
  ],
  fieldSources: (endpoint = "oil-gas-fields", id, field) => [
    ...resourceKeys.detail(endpoint, id),
    "field-sources",
    field,
  ],
  views: (endpoint = "resources") => [...resourceKeys.all(endpoint), "view"],
  view: (endpoint = "resources", id) => [...resourceKeys.views(endpoint), id],

  mergeCandidates: (endpoint = "oil-gas-fields") => [
    endpoint,
    "merge-candidates",
  ],
  mergeCandidate: (endpoint = "oil-gas-fields", id) => [
    endpoint,
    "merge-candidates",
    id,
  ],
  preview: (endpoint = "oil-gas-fields", id) => [
    endpoint,
    "merge-candidates",
    id,
    "preview",
  ],
};

// Query definitions
export const resourceQueries = {
  list: (
    config,
    endpoint = "resources",
    page = DEFAULT_PAGE,
    page_size = DEFAULT_PAGE_SIZE,
    filters = {},
    q,
    sort_by,
    sort_order,
  ) => ({
    queryKey: resourceKeys.list(endpoint, {
      page,
      page_size,
      ...filters,
      q,
      sort_by,
      sort_order,
    }),
    queryFn: (fetcher) =>
      getResources(config, fetcher, endpoint, {
        page,
        page_size,
        filters,
        q,
        sort_by,
        sort_order,
      }),
    enabled: false,
    staleTime: DEFAULT_STALE_TIME,
  }),

  filterOptions: (config, endpoint = "resources", field) => ({
    queryKey: resourceKeys.filterOptions(endpoint, field),
    queryFn: (fetcher) =>
      getResourceFilterOptions(config, fetcher, endpoint, field),
    enabled: false,
    staleTime: DEFAULT_STALE_TIME,
  }),

  detail: (config, endpoint = "resources", id) => ({
    queryKey: resourceKeys.detail(endpoint, id),
    queryFn: (fetcher) => getResourceDetail(config, id, fetcher, endpoint),
    enabled: false,
  }),

  fieldSources: (config, endpoint = "oil-gas-fields", id, field) => ({
    queryKey: resourceKeys.fieldSources(endpoint, id, field),
    queryFn: (fetcher) =>
      getFieldSourceValues(config, id, field, fetcher, endpoint),
    enabled: false,
    staleTime: DEFAULT_STALE_TIME,
  }),

  view: (config, endpoint = "resources", id) => ({
    queryKey: resourceKeys.view(endpoint, id),
    queryFn: (fetcher) => getResource(config, id, fetcher, endpoint),
    enabled: false,
  }),

  mergeCandidates: (config, endpoint = "oil-gas-fields") => ({
    queryKey: resourceKeys.mergeCandidates(endpoint),
    queryFn: (fetcher) => getMergeCandidates(config, fetcher, endpoint),
    enabled: false,
  }),

  mergeCandidate: (config, endpoint = "oil-gas-fields", id) => ({
    queryKey: resourceKeys.mergeCandidate(endpoint, id),
    queryFn: (fetcher) => getMergeCandidate(config, id, fetcher, endpoint),
    enabled: false,
  }),
  mergeCandidatePreview: (config, endpoint = "oil-gas-fields", id) => ({
    queryKey: resourceKeys.preview(endpoint, id),
    queryFn: (fetcher) =>
      getMergeCandidatePreview(config, id, fetcher, endpoint),
    enabled: false,
  }),
};
