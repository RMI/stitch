import { expect, afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers);

afterEach(() => {
  cleanup();
});

vi.mock("@auth0/auth0-react", () => ({
  useAuth0: vi.fn().mockReturnValue({
    isAuthenticated: true,
    isLoading: false,
    error: null,
    user: { sub: "test-user-id", email: "test@example.com" },
    getAccessTokenSilently: vi.fn().mockResolvedValue("test-access-token"),
    loginWithRedirect: vi.fn(),
    logout: vi.fn(),
  }),
  Auth0Provider: ({ children }) => children,
}));
