import config from "../config/env";

/**
 * Returns a `fetch`-compatible function that automatically attaches a Bearer
 * token to every request. The token is acquired on each call via Auth0's
 * `getAccessTokenSilently`, so callers never handle tokens directly.
 *
 * @param {Function} getAccessTokenSilently - Auth0 SDK method for obtaining
 *   an access token without user interaction.
 * @returns {Function} An async `(url, options?) => Response` fetcher.
 */
export function createAuthenticatedFetcher(getAccessTokenSilently) {
  return async (url, options = {}) => {
    const token = await getAccessTokenSilently({
      authorizationParams: { audience: config.auth0.audience },
    });
    const headers = new Headers(options.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(url, { ...options, headers });
  };
}
