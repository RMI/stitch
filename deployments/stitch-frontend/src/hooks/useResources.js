import { useAuth0 } from "@auth0/auth0-react";
import { useQuery } from "@tanstack/react-query";
import { resourceQueries } from "../queries/resources";

export function useResources() {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();
  return useQuery({
    ...resourceQueries.list(getAccessTokenSilently),
    enabled: isAuthenticated,
  });
}

export function useResource(id) {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();
  return useQuery({
    ...resourceQueries.detail(id, getAccessTokenSilently),
    enabled: isAuthenticated && !!id,
  });
}
