import { useMutation } from "@tanstack/react-query";
import { useAuth0 } from "@auth0/auth0-react";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";

/**
 * Wraps `useMutation` so that every request carries a valid Auth0 bearer token.
 *
 * The mutation-side counterpart to `useAuthenticatedQuery`: callers provide a
 * `mutationFn(fetcher, variables)` instead of a plain `mutationFn(variables)`.
 * The hook builds an authenticated fetcher (via `createAuthenticatedFetcher`)
 * and passes it in, keeping token acquisition out of individual mutations.
 *
 * @param {object} mutationOptions - Standard TanStack Mutation options, except
 *   `mutationFn` receives an authenticated `fetcher` as its first argument.
 */
export function useAuthenticatedMutation(mutationOptions) {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const fetcher = createAuthenticatedFetcher(config, getAccessTokenSilently);
  const { mutationFn, ...rest } = mutationOptions;
  return useMutation({
    ...rest,
    mutationFn: (variables) => mutationFn(fetcher, variables),
  });
}
