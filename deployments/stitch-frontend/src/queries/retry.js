/**
 * Which query failures are worth another attempt.
 *
 * Most deployments let their Container Apps scale to zero when idle, so the
 * first request after a quiet period arrives while the container is still
 * starting. Azure holds the request during activation and answers with a 5xx if
 * the replica is not ready in time, or drops the connection outright -- which
 * `fetch` surfaces as a TypeError. Both deserve another attempt a moment later.
 *
 * A 4xx does not: the request itself was wrong, and re-sending it unchanged
 * fails identically while making the user wait longer for the same error.
 */

/** Retries after the initial attempt, so a query is tried at most 4 times. */
export const MAX_RETRIES = 3;

/**
 * @param {unknown} error - The error a query function threw.
 * @returns {boolean} Whether the failure looks transient.
 */
export function isRetriableError(error) {
  const status = error?.status;

  if (typeof status === "number") {
    // 408 and 429 are transient by definition; 5xx covers a container that was
    // not ready in time.
    return status === 408 || status === 429 || status >= 500;
  }

  // No HTTP status means the request never completed. A failed `fetch` rejects
  // with a TypeError in every browser ("Failed to fetch" in Chrome,
  // "NetworkError when attempting to fetch resource." in Firefox). Anything
  // else reaching here -- an auth-flow rejection, a bug in a query function --
  // is not a cold start and gains nothing from being repeated.
  return error instanceof TypeError;
}

/**
 * `retry` predicate for TanStack Query. Called after each failure with the
 * running failure count, starting at 1.
 *
 * @param {number} failureCount - How many times this query has failed so far.
 * @param {unknown} error - The most recent error.
 * @returns {boolean} Whether to try again.
 */
export function shouldRetryQuery(failureCount, error) {
  return failureCount <= MAX_RETRIES && isRetriableError(error);
}
