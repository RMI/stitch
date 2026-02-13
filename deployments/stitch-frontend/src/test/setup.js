import { expect, afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import { vi } from "vitest";

vi.mock("@auth0/auth0-react", () => {
  return {
    Auth0Provider: ({ children }) => children,
    useAuth0: () => ({
      isLoading: false,
      isAuthenticated: true,
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
      getAccessTokenSilently: vi.fn(async () => "test-token"),
    }),
  };
});

expect.extend(matchers);

afterEach(() => {
  cleanup();
});
