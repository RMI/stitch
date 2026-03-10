import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { ogfieldQueries } from "../queries/ogfields";

export function useOGFields() {
  return useAuthenticatedQuery(ogfieldQueries.list());
}

export function useOGField(id) {
  return useAuthenticatedQuery(ogfieldQueries.detail(id));
}
