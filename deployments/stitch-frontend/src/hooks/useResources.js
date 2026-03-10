import { useQuery } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { resourceQueries, resourceKeys } from "../queries/resources";
import mockResources from "../mockData/og_field_resources.json";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

//--------------------------------
// Real Implementations
//--------------------------------
function useResourcesReal() {
  return useAuthenticatedQuery(resourceQueries.list());
}

function useResourceReal(id) {
  return useAuthenticatedQuery(resourceQueries.detail(id));
}

//--------------------------------
// Mock Implementations
//--------------------------------
function useResourcesMock() {
  return useQuery({
    queryKey: resourceKeys.lists(),
    queryFn: () => Promise.resolve(mockResources),
    enabled: false,
  });
}

function useResourceMock(id) {
  return useQuery({
    queryKey: resourceKeys.detail(id),
    queryFn: () =>
      Promise.resolve(mockResources.find((r) => r.id === id) ?? null),
    enabled: false,
  });
}

// Export one implementation based on the compile-time flag. Assign at module level
export const useResources = USE_MOCK_DATA ? useResourcesMock : useResourcesReal;
export const useResource = USE_MOCK_DATA ? useResourceMock : useResourceReal;
