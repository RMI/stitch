import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { resourceQueries } from "../queries/resources";

export function useResources() {
  return useAuthenticatedQuery(resourceQueries.list());
}

export function useResource(id) {
  return useAuthenticatedQuery(resourceQueries.detail(id));
}
