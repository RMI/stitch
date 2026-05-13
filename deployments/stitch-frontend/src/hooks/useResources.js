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
      sort_by,
      sort_order,
    ),
    enabled,
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

function getMockResourcePage({
  page = DEFAULT_PAGE,
  page_size = DEFAULT_PAGE_SIZE,
  filters = {},
  sort_by,
  sort_order,
}) {
  const filtered = applyMockFilters(MOCK_RESOURCE_ITEMS, filters);
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

function useResourcesMock(
  endpoint = "resources",
  {
    page = DEFAULT_PAGE,
    page_size = DEFAULT_PAGE_SIZE,
    enabled = true,
    filters = {},
    sort_by,
    sort_order,
  } = {},
) {
  return useQuery({
    queryKey: resourceKeys.list(endpoint, {
      page,
      page_size,
      ...filters,
      sort_by,
      sort_order,
    }),
    queryFn: () =>
      Promise.resolve(
        getMockResourcePage({ page, page_size, filters, sort_by, sort_order }),
      ),
    enabled,
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

function useMergeCandidatePreviewMock(
  endpoint = "oil-gas-fields",
  id,
  enabled = false,
) {
  return useQuery({
    queryKey: resourceKeys.preview(endpoint, id),
    queryFn: () => Promise.resolve(null),
    enabled,
  });
}

function useMergeCandidatePreviewReal(
  endpoint = "oil-gas-fields",
  id,
  enabled = false,
) {
  const config = useConfig();
  return useAuthenticatedQuery({
    ...resourceQueries.mergeCandidatePreview(config, endpoint, id),
    enabled,
  });
}

// Export one implementation based on the compile-time flag. Assign at module level
export const useResources = USE_MOCK_DATA ? useResourcesMock : useResourcesReal;
export const useResource = USE_MOCK_DATA ? useResourceMock : useResourceReal;
export const useResourceDetail = USE_MOCK_DATA
  ? useResourceDetailMock
  : useResourceDetailReal;
export const useMergeCandidates = USE_MOCK_DATA
  ? useMergeCandidatesMock
  : useMergeCandidatesReal;
export const useMergeCandidate = USE_MOCK_DATA
  ? useMergeCandidateMock
  : useMergeCandidateReal;
export const useMergeCandidatePreview = USE_MOCK_DATA
  ? useMergeCandidatePreviewMock
  : useMergeCandidatePreviewReal;
