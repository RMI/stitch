import { describe, it, expect } from "vitest";
import { MAX_RETRIES, isRetriableError, shouldRetryQuery } from "./retry";

function httpError(status) {
  const error = new Error(`HTTP error! status: ${status}`);
  error.status = status;
  return error;
}

describe("isRetriableError", () => {
  it.each([500, 502, 503, 504])(
    "retries %i (container still starting)",
    (s) => {
      expect(isRetriableError(httpError(s))).toBe(true);
    },
  );

  it.each([408, 429])("retries %i (transient by definition)", (s) => {
    expect(isRetriableError(httpError(s))).toBe(true);
  });

  it.each([400, 401, 403, 404, 422])("does not retry %i", (s) => {
    expect(isRetriableError(httpError(s))).toBe(false);
  });

  it("retries a failed fetch, which rejects with a TypeError", () => {
    expect(isRetriableError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("does not retry an error with no status that is not a fetch failure", () => {
    expect(isRetriableError(new Error("login_required"))).toBe(false);
  });

  it("does not blow up on a null or undefined error", () => {
    expect(isRetriableError(null)).toBe(false);
    expect(isRetriableError(undefined)).toBe(false);
  });
});

describe("shouldRetryQuery", () => {
  it("keeps retrying a transient failure up to the cap", () => {
    for (let failureCount = 1; failureCount <= MAX_RETRIES; failureCount++) {
      expect(shouldRetryQuery(failureCount, httpError(503))).toBe(true);
    }
  });

  it("stops once the cap is exceeded, even while still failing transiently", () => {
    expect(shouldRetryQuery(MAX_RETRIES + 1, httpError(503))).toBe(false);
  });

  it("does not retry a client error even on the first failure", () => {
    expect(shouldRetryQuery(1, httpError(404))).toBe(false);
  });
});
