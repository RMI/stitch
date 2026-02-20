import { useQuery } from "@tanstack/react-query";
import { useAuth0 } from "@auth0/auth0-react";
import { createAuthenticatedFetcher } from "../auth/api";

/**
 * Wraps `useQuery` so that every request carries a valid Auth0 bearer token.
 *
 * Callers provide a `queryFn(fetcher)` instead of a plain `queryFn()`. The
 * hook builds an authenticated fetcher (via `createAuthenticatedFetcher`) and
 * passes it into `queryFn`, keeping token acquisition out of individual query
 * functions.
 *
 * @param {object} queryOptions - Standard TanStack Query options, except
 *   `queryFn` receives an authenticated `fetcher` as its first argument.
 */
export function useAuthenticatedQuery(queryOptions) {
  const { getAccessTokenSilently } = useAuth0();
  const fetcher = createAuthenticatedFetcher(getAccessTokenSilently);
  const { queryFn, ...rest } = queryOptions;
  return useQuery({ ...rest, queryFn: () => queryFn(fetcher) });
}
