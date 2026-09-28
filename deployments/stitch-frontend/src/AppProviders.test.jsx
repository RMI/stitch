import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useQueryClient } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import { AppProviders } from "./AppProviders";

// The global mock in test/setup.js replaces Auth0Provider with a prop-dropping
// pass-through, so props can't be asserted through it. Re-mock locally (same
// per-file pattern used for react-router-dom in ResourceDetailPage.test.jsx),
// capturing Auth0Provider as a spy while keeping useAuth0 authenticated so
// AuthGate renders children.
vi.mock("@auth0/auth0-react", () => ({
  Auth0Provider: vi.fn(({ children }) => children),
  useAuth0: vi.fn().mockReturnValue({
    isAuthenticated: true,
    isLoading: false,
    error: null,
    user: { sub: "test-user-id", email: "test@example.com" },
    getAccessTokenSilently: vi.fn().mockResolvedValue("test-access-token"),
    loginWithRedirect: vi.fn(),
    logout: vi.fn(),
  }),
}));

const TEST_CONFIG = {
  auth0: {
    domain: "example.auth0.com",
    clientId: "client-id",
    audience: "https://stitch-api.local",
  },
};

describe("AppProviders", () => {
  it("persists the Auth0 session across reloads (STIT-581)", () => {
    render(
      <AppProviders config={TEST_CONFIG}>
        <div>App Content</div>
      </AppProviders>,
    );

    // cacheLocation="localstorage" + useRefreshTokens keeps the refresh token
    // across a page reload, so the session re-hydrates instead of falling back
    // to the Login screen.
    expect(Auth0Provider).toHaveBeenCalledTimes(1);
    expect(Auth0Provider.mock.calls[0][0]).toMatchObject({
      cacheLocation: "localstorage",
      useRefreshTokens: true,
    });
  });

  it("hands the cold-start retry policy down to every query", () => {
    // The predicate itself is unit-tested in queries/retry.test.js, but nothing
    // otherwise proves it reaches the app: renderWithQueryClient builds its own
    // client with `retry: false`, so component tests never exercise this
    // default. Without this test, dropping the wiring keeps the suite green and
    // only surfaces as failed first loads against a sleeping container.
    let defaults;
    function Probe() {
      defaults = useQueryClient().getDefaultOptions();
      return null;
    }

    render(
      <AppProviders config={TEST_CONFIG}>
        <Probe />
      </AppProviders>,
    );

    const retry = defaults.queries?.retry;

    // A number here would mean someone reverted to `retry: 1`; undefined would
    // mean the option was dropped, restoring TanStack's default of retrying
    // everything three times, 4xx included.
    expect(typeof retry).toBe("function");

    const httpError = (status) => Object.assign(new Error(status), { status });

    expect(retry(1, httpError(503))).toBe(true);
    expect(retry(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(retry(1, httpError(404))).toBe(false);
    expect(retry(99, httpError(503))).toBe(false);

    // Mutations are deliberately left on the default of no retries: replaying a
    // non-idempotent write after a timeout is worse than the error.
    expect(defaults.mutations?.retry).toBeUndefined();
  });

  it("renders children through AuthGate when authenticated", () => {
    render(
      <AppProviders config={TEST_CONFIG}>
        <div>App Content</div>
      </AppProviders>,
    );

    expect(screen.getByText("App Content")).toBeInTheDocument();
  });
});
