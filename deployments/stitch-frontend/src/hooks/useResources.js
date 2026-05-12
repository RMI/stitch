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

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

//--------------------------------
// Real Implementations
//--------------------------------
function useResourcesReal(
  endpoint = "resources",
  {
    page = DEFAULT_PAGE,
    page_size = DEFAULT_PAGE_SIZE,
    enabled = false,
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
function useResourcesMock(
  endpoint = "resources",
  { page = DEFAULT_PAGE, page_size = DEFAULT_PAGE_SIZE } = {},
) {
  return useQuery({
    queryKey: resourceKeys.list(endpoint, { page, page_size }),
    queryFn: () => Promise.resolve(mockResources),
    enabled: false,
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
export const useSourceDetail = USE_MOCK_DATA
  ? useSourceDetailMock
  : useSourceDetailReal;
export const useMergeCandidates = USE_MOCK_DATA
  ? useMergeCandidatesMock
  : useMergeCandidatesReal;
export const useMergeCandidate = USE_MOCK_DATA
  ? useMergeCandidateMock
  : useMergeCandidateReal;
export const useMergeCandidatePreview = USE_MOCK_DATA
  ? useMergeCandidatePreviewMock
  : useMergeCandidatePreviewReal;
