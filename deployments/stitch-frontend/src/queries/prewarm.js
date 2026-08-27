/**
 * Wake the backend before the user needs it.
 *
 * Most deployments let their Container Apps scale to zero when idle (see
 * `deployments/CI_DEPLOYMENTS.md`), so the first request of a session pays a
 * cold start. Bootstrap is the earliest useful moment to trigger one: it runs
 * before Auth0 mounts, so the container starts while the user is still being
 * redirected through login, and by the time the first real query fires the API
 * may already be serving.
 */

// `/health/details` rather than `/health`: it resolves the database engine, so
// it opens a connection too. The container starting and the connection pool
// filling are the two costs of a cold start, and this pays both during dead
// time. Neither endpoint requires auth.
const HEALTH_PATH = "/health/details";

function healthUrl(baseUrl) {
  return `${baseUrl.replace(/\/+$/, "")}${HEALTH_PATH}`;
}

/**
 * Send a throwaway request to the API so its container starts.
 *
 * @param {object} config - Resolved runtime config.
 * @returns {Promise<void>} Always resolves. A prewarm that fails has cost the
 *   user nothing, so there is no error to report and nothing to retry -- the
 *   real request behind it carries its own retry policy (see `retry.js`).
 */
export function prewarmApi(config) {
  const baseUrl = config?.apiBaseUrl;

  // `loadConfig` already rejects a non-string `apiUrl`, so this only guards
  // callers that build a config by hand. It is here because the contract above
  // says this never rejects, and `main.jsx` relies on that: a synchronous throw
  // would escape `bootstrap()` and swap the app for the config-error screen.
  if (typeof baseUrl !== "string" || !baseUrl) {
    return Promise.resolve();
  }

  // Deliberately not aborted on a timer: Azure holds the request open while it
  // activates a replica, and that wait is the thing doing the work.
  //
  // Deliberately unauthenticated and header-free, which keeps this a
  // CORS-simple request. It reaches the server without a preflight even when
  // the deployment's single allowed origin does not match the browser's -- and
  // since the response is discarded, being blocked from reading it costs
  // nothing. That matters while a custom domain is being cut over.
  return fetch(healthUrl(baseUrl), { cache: "no-store" }).then(
    () => undefined,
    () => undefined,
  );
}
