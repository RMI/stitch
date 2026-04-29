import { expect, afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import { resetConfigForTests, setConfigForTests } from "../config/env";

expect.extend(matchers);

const TEST_CONFIG = {
  appEnv: "test",
  apiBaseUrl: "http://localhost:8000/api/v1",
  entityLinkageBaseUrl: "http://localhost:8001/api/v1",
  auth0: {
    domain: "example.auth0.com",
    clientId: "client-id",
    audience: "https://stitch-api.local",
  },
  build: {
    appVersion: "0.0.0-test",
    buildId: "test-build",
    gitSha: "abcdef1",
    nodeVersion: "v20.0.0",
    viteVersion: "7.2.4",
    buildTime: "2026-04-17T10:00:00Z",
  },
};

beforeEach(() => {
  setConfigForTests(TEST_CONFIG);
});

afterEach(() => {
  cleanup();
  resetConfigForTests();
  vi.clearAllMocks();
  vi.restoreAllMocks();
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
