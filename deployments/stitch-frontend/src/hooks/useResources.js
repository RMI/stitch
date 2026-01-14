import { useQuery } from "@tanstack/react-query";
import { resourceQueries } from "../queries/resources";

export function useResources() {
  return useQuery(resourceQueries.list());
}

export function useResource(id) {
  return useQuery(resourceQueries.detail(id));
}
