import { keepPreviousData, queryOptions } from "@tanstack/react-query";
import {
  getResourceFilterOptions,
  getResource,
  getResources,
  getResourceDetail,
  getFieldSourceValues,
  getMergeCandidates,
  getMergeCandidate,
} from "./api";

export const DEFAULT_STALE_TIME = 60_000;
export const DEFAULT_PAGE = 1;
export const DEFAULT_PAGE_SIZE = 10;

// Private key builders, hierarchical for easy invalidation. Not exported:
// every queryKey a caller could need comes back attached to the matching
// resourceQueries factory below, so a key and its fetcher can never drift
// apart the way a separately-maintained registry allowed.
//
// Every key here is prefixed by [endpoint] — mutations rely on that
// invariant to invalidate a whole endpoint's cache with a single-segment
// key. resources.test.js guards it; keep any new factory prefixed the same
// way.
const keys = {
  all: (endpoint = "resources") => [endpoint],
  lists: (endpoint = "resources") => [...keys.all(endpoint), "list"],
  list: (endpoint = "resources", filters) => [...keys.lists(endpoint), filters],
  filterOptions: (endpoint = "resources", field) => [
    ...keys.all(endpoint),
    "filter-options",
    field,
  ],
  details: (endpoint = "resources") => [...keys.all(endpoint), "detail"],
  detail: (endpoint = "resources", id) => [...keys.details(endpoint), id],
  fieldSources: (endpoint = "oil-gas-fields", id, field) => [
    ...keys.detail(endpoint, id),
    "field-sources",
    field,
  ],
  views: (endpoint = "resources") => [...keys.all(endpoint), "view"],
  view: (endpoint = "resources", id) => [...keys.views(endpoint), id],
  mergeCandidates: (endpoint = "oil-gas-fields") => [
    ...keys.all(endpoint),
    "merge-candidates",
  ],
  mergeCandidate: (endpoint = "oil-gas-fields", id) => [
    ...keys.mergeCandidates(endpoint),
    id,
  ],
};

// Query definitions. Each factory returns queryKey + queryFn + options
// together; the same object is what a hook passes to useQuery and what a
// caller reads .queryKey off of to invalidate/reset/setQueryData that exact
// query. Gating (enabled) is a hook-layer concern — see useResources.js —
// so it isn't set here.
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
  ) =>
    queryOptions({
      queryKey: keys.list(endpoint, {
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
      staleTime: DEFAULT_STALE_TIME,
      // Keeps showing the previous page's rows (dimmed, in ResourcesTable)
      // while a new page/filter/sort combination fetches, instead of the
      // table flashing to empty for the duration of the request.
      placeholderData: keepPreviousData,
    }),

  filterOptions: (config, endpoint = "resources", field) =>
    queryOptions({
      queryKey: keys.filterOptions(endpoint, field),
      queryFn: (fetcher) =>
        getResourceFilterOptions(config, fetcher, endpoint, field),
      staleTime: DEFAULT_STALE_TIME,
    }),

  detail: (config, endpoint = "resources", id) =>
    queryOptions({
      queryKey: keys.detail(endpoint, id),
      queryFn: (fetcher) => getResourceDetail(config, id, fetcher, endpoint),
    }),

  fieldSources: (config, endpoint = "oil-gas-fields", id, field) =>
    queryOptions({
      queryKey: keys.fieldSources(endpoint, id, field),
      queryFn: (fetcher) =>
        getFieldSourceValues(config, id, field, fetcher, endpoint),
      staleTime: DEFAULT_STALE_TIME,
    }),

  view: (config, endpoint = "resources", id) =>
    queryOptions({
      queryKey: keys.view(endpoint, id),
      queryFn: (fetcher) => getResource(config, id, fetcher, endpoint),
    }),

  mergeCandidates: (config, endpoint = "oil-gas-fields") =>
    queryOptions({
      queryKey: keys.mergeCandidates(endpoint),
      queryFn: (fetcher) => getMergeCandidates(config, fetcher, endpoint),
    }),

  mergeCandidate: (config, endpoint = "oil-gas-fields", id) =>
    queryOptions({
      queryKey: keys.mergeCandidate(endpoint, id),
      queryFn: (fetcher) => getMergeCandidate(config, id, fetcher, endpoint),
    }),
};
