import { useQuery } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { useConfig } from "../config/useConfig";
import {
  resourceQueries,
  resourceKeys,
  DEFAULT_PAGE_SIZE,
  DEFAULT_PAGE,
} from "../queries/resources";
import mockResources from "../mockData/og_field_resources.json";
import {
  getResourceField,
  normalizeResourceListItem,
} from "../utils/resourceDisplay";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
const MOCK_RESOURCE_ITEMS = mockResources.map(normalizeResourceListItem);

//--------------------------------
// Real Implementations
//--------------------------------
function useResourcesReal(
  endpoint = "resources",
  {
    page = DEFAULT_PAGE,
    page_size = DEFAULT_PAGE_SIZE,
    enabled = true,
    filters = {},
    q,
    sort_by,
    sort_order,
  } = {},
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.list(
      config,
      endpoint,
      page,
      page_size,
      filters,
      q,
      sort_by,
      sort_order,
    ),
    enabled,
  });
}

function useResourceFilterOptionsReal(
  endpoint = "resources",
  field,
  enabled = true,
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.filterOptions(config, endpoint, field),
    enabled: enabled && Boolean(field),
  });
}

function useResourceReal(endpoint = "resources", id, enabled = false) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.view(config, endpoint, id),
    enabled,
  });
}

function useResourceDetailReal(endpoint = "resources", id, enabled = false) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.detail(config, endpoint, id),
    enabled,
  });
}

function useSourceDetailReal(
  endpoint = "oil-gas-field-sources",
  id,
  enabled = false,
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.detail(config, endpoint, id),
    enabled,
  });
}

function useFieldSourceValuesReal(
  endpoint = "oil-gas-fields",
  id,
  field,
  enabled = false,
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.fieldSources(config, endpoint, id, field),
    enabled: enabled && Boolean(field) && Number.isFinite(id),
  });
}

function useMergeCandidatesReal(endpoint = "oil-gas-fields", enabled = false) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.mergeCandidates(config, endpoint),
    enabled,
  });
}

function useMergeCandidateReal(
  endpoint = "oil-gas-fields",
  id,
  enabled = false,
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.mergeCandidate(config, endpoint, id),
    enabled,
  });
}

//--------------------------------
// Mock Implementations
//--------------------------------
function applyMockFilters(resources, filters = {}) {
  return resources.filter((resource) =>
    Object.entries(filters).every(([field, selected]) => {
      if (!selected?.length) return true;

      const value = getResourceField(resource, field);
      if (value == null) return false;

      return selected.map(String).includes(String(value));
    }),
  );
}

function compareResourceIds(aId, bId) {
  if (aId == null && bId == null) return 0;
  if (aId == null) return 1;
  if (bId == null) return -1;

  return String(aId).localeCompare(String(bId), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function compareMockResources(a, b, field, sortOrder = "asc") {
  const aValue = getResourceField(a, field);
  const bValue = getResourceField(b, field);
  const direction = sortOrder === "desc" ? -1 : 1;

  if (aValue == null && bValue == null) return compareResourceIds(a.id, b.id);
  if (aValue == null) return 1;
  if (bValue == null) return -1;

  if (typeof aValue === "number" && typeof bValue === "number") {
    return (aValue - bValue) * direction;
  }

  return String(aValue).localeCompare(String(bValue)) * direction;
}

const MOCK_SEARCH_FIELDS = [
  "name",
  "name_local",
  "basin",
  "state_province",
  "region",
];

function applyMockSearch(resources, q) {
  const term = q?.trim().toLowerCase();
  if (!term) return resources;

  return resources.filter((resource) =>
    MOCK_SEARCH_FIELDS.some((field) => {
      const value = getResourceField(resource, field);
      return value != null && String(value).toLowerCase().includes(term);
    }),
  );
}

function getMockResourcePage({
  page = DEFAULT_PAGE,
  page_size = DEFAULT_PAGE_SIZE,
  filters = {},
  q,
  sort_by,
  sort_order,
}) {
  const searched = applyMockSearch(MOCK_RESOURCE_ITEMS, q);
  const filtered = applyMockFilters(searched, filters);
  const sorted = sort_by
    ? [...filtered].sort((a, b) =>
        compareMockResources(a, b, sort_by, sort_order),
      )
    : filtered;
  const start = (page - 1) * page_size;
  const items = sorted.slice(start, start + page_size);

  return {
    items,
    total_count: sorted.length,
    page,
    page_size,
    total_pages: Math.ceil(sorted.length / page_size),
  };
}

function getMockFilterOptions(field) {
  const values = Array.from(
    new Set(
      MOCK_RESOURCE_ITEMS.map((resource) => getResourceField(resource, field))
        .filter((value) => value != null && value !== "")
        .map(String),
    ),
  ).sort((a, b) => a.localeCompare(b));

  return { field, values };
}

function useResourcesMock(
  endpoint = "resources",
  {
    page = DEFAULT_PAGE,
    page_size = DEFAULT_PAGE_SIZE,
    enabled = true,
    filters = {},
    q,
    sort_by,
    sort_order,
  } = {},
) {
  return useQuery({
    queryKey: resourceKeys.list(endpoint, {
      page,
      page_size,
      ...filters,
      q,
      sort_by,
      sort_order,
    }),
    queryFn: () =>
      Promise.resolve(
        getMockResourcePage({
          page,
          page_size,
          filters,
          q,
          sort_by,
          sort_order,
        }),
      ),
    enabled,
  });
}

function useResourceFilterOptionsMock(
  endpoint = "resources",
  field,
  enabled = true,
) {
  return useQuery({
    queryKey: resourceKeys.filterOptions(endpoint, field),
    queryFn: () => Promise.resolve(getMockFilterOptions(field)),
    enabled: enabled && Boolean(field),
  });
}

function useResourceMock(endpoint = "resources", id, enabled = false) {
  return useQuery({
    queryKey: resourceKeys.detail(endpoint, id),
    queryFn: () =>
      Promise.resolve(mockResources.find((r) => r.id === id) ?? null),
    enabled,
  });
}

function useResourceDetailMock(endpoint = "resources", id, enabled = false) {
  return useQuery({
    queryKey: resourceKeys.detail(endpoint, id),
    queryFn: () =>
      Promise.resolve(mockResources.find((r) => r.id === id) ?? null),
    enabled,
  });
}

function useSourceDetailMock(
  endpoint = "oil-gas-field-sources",
  id,
  enabled = false,
) {
  return useQuery({
    queryKey: resourceKeys.detail(endpoint, id),
    queryFn: () => Promise.resolve(null),
    enabled,
  });
}

function useFieldSourceValuesMock(
  endpoint = "oil-gas-fields",
  id,
  field,
  enabled = false,
) {
  // Mock mode has no backend; the panel degrades to an empty state, matching
  // useSourceDetailMock. Real behavior is exercised against the API. Guard `id`
  // the same way the real hook does so the query key stays stable.
  return useQuery({
    queryKey: resourceKeys.fieldSources(endpoint, id, field),
    queryFn: () => Promise.resolve([]),
    enabled: enabled && Boolean(field) && Number.isFinite(id),
  });
}

function useMergeCandidatesMock(endpoint = "oil-gas-fields", enabled = false) {
  return useQuery({
    queryKey: resourceKeys.mergeCandidates(endpoint),
    queryFn: () => Promise.resolve([]),
    enabled,
  });
}

function useMergeCandidateMock(
  endpoint = "oil-gas-fields",
  id,
  enabled = false,
) {
  return useQuery({
    queryKey: resourceKeys.mergeCandidate(endpoint, id),
    queryFn: () => Promise.resolve(null),
    enabled,
  });
}

// Export one implementation based on the compile-time flag. Assign at module level
export const useResources = USE_MOCK_DATA ? useResourcesMock : useResourcesReal;
export const useResourceFilterOptions = USE_MOCK_DATA
  ? useResourceFilterOptionsMock
  : useResourceFilterOptionsReal;
export const useResource = USE_MOCK_DATA ? useResourceMock : useResourceReal;
export const useResourceDetail = USE_MOCK_DATA
  ? useResourceDetailMock
  : useResourceDetailReal;
export const useSourceDetail = USE_MOCK_DATA
  ? useSourceDetailMock
  : useSourceDetailReal;
export const useFieldSourceValues = USE_MOCK_DATA
  ? useFieldSourceValuesMock
  : useFieldSourceValuesReal;
export const useMergeCandidates = USE_MOCK_DATA
  ? useMergeCandidatesMock
  : useMergeCandidatesReal;
export const useMergeCandidate = USE_MOCK_DATA
  ? useMergeCandidateMock
  : useMergeCandidateReal;
