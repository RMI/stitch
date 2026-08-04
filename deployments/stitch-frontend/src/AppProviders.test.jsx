import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

  it("renders children through AuthGate when authenticated", () => {
    render(
      <AppProviders config={TEST_CONFIG}>
        <div>App Content</div>
      </AppProviders>,
    );

    expect(screen.getByText("App Content")).toBeInTheDocument();
  });
});
