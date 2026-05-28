import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { setConfigForTests } from "../config/env";
import { renderWithQueryClient } from "../test/utils";

function createMockConfig() {
  return {
    appEnv: "local",
    apiBaseUrl: "http://localhost:8000/api/v1",
    entityLinkageBaseUrl: "http://localhost:8001/api/v1",
    auth0: {
      domain: "example.auth0.com",
      clientId: "client-id",
      audience: "https://stitch-api.local",
    },
    build: {
      appVersion: "0.0.0",
      buildId: "local-build",
      gitSha: "abcdef1",
      nodeVersion: "v20.19.0",
      viteVersion: "^7.2.4",
      buildTime: "2026-04-06T12:00:00Z",
    },
  };
}

describe("ColophonPanel", () => {
  let fetchMock;
  let clipboardSpy;
  let getAccessTokenSilently;
  let mockConfig;

  beforeEach(() => {
    mockConfig = createMockConfig();
    setConfigForTests(mockConfig);
    getAccessTokenSilently = vi.fn().mockResolvedValue("test-access-token");

    vi.mocked(useAuth0).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      error: null,
      user: { sub: "test-user-id", email: "test@example.com" },
      getAccessTokenSilently,
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    });

    fetchMock = vi.fn().mockImplementation((url) => {
      if (url === "http://localhost:8000/api/v1/health/details") {
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue({
            status: "ok",
            service: "stitch-api",
            runtime: {
              environment: "dev",
              started_at: "2026-04-06T10:00:00Z",
              uptime_seconds: 123.456,
            },
            auth: {
              disabled: false,
              startup_validated: true,
            },
            frontend: {
              origin: "http://localhost:3000",
            },
            database: {
              dialect: "postgresql",
              host: "localhost",
              port: 5432,
              database: "stitch",
              reachable: true,
            },
            build: {
              app_version: "0.1.0",
              build_id: "api-local",
              git_sha: "1234567890abcdef",
              build_time: "2026-04-06T09:59:00Z",
            },
          }),
        });
      }

      if (url === "http://localhost:8000/api/v1/auth/me") {
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue({
            user: {
              id: 7,
              sub: "auth0|test-user-id",
              role: null,
              email: "test@example.com",
              name: "Test User",
            },
            claims: {
              sub: "auth0|test-user-id",
              email: "test@example.com",
              name: "Test User",
              permissions: ["resource:read", "source:read:wm"],
              raw: {
                permissions: ["resource:read", "source:read:wm"],
              },
            },
          }),
        });
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    if (!navigator.clipboard) {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: vi.fn(),
        },
      });
    }

    clipboardSpy = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined);

    Object.defineProperty(navigator, "language", {
      configurable: true,
      value: "en-US",
    });

    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: "VitestBrowser/1.0",
    });

    Object.defineProperty(navigator, "connection", {
      configurable: true,
      value: {
        effectiveType: "4g",
        downlink: 10,
      },
    });

    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1440,
    });

    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: 900,
    });

    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: 2,
    });
  });

  afterEach(() => {
    clipboardSpy?.mockRestore();
    vi.unstubAllGlobals();
  });

  it("renders frontend, backend, and runtime diagnostics", async () => {
    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen />);

    expect(screen.getByText("Frontend Build Info")).toBeInTheDocument();
    expect(screen.getByText("Backend Diagnostics")).toBeInTheDocument();
    expect(screen.getByText("Runtime Info")).toBeInTheDocument();

    expect(
      screen.getByText("http://localhost:8000/api/v1"),
    ).toBeInTheDocument();
    expect(screen.getByText("local-build")).toBeInTheDocument();
    expect(screen.getByText("abcdef1")).toBeInTheDocument();
    expect(screen.getByText("v20.19.0")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("stitch-api")).toBeInTheDocument();
    });

    expect(screen.getByText("postgresql")).toBeInTheDocument();
    const reachableLabel = screen.getByText("DB Reachable");
    expect(reachableLabel.closest("div")).toHaveTextContent("true");
    const validatedLabel = screen.getByText("Auth Validated");
    expect(validatedLabel.closest("div")).toHaveTextContent("true");
    expect(screen.getByText("VitestBrowser/1.0")).toBeInTheDocument();
    expect(screen.getByText("1440x900")).toBeInTheDocument();
    expect(screen.getByText("2x")).toBeInTheDocument();
    expect(screen.getByText("4g (10 Mbps)")).toBeInTheDocument();
    expect(screen.getByText("Auth Claims Status")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("auth0|test-user-id")).toBeInTheDocument();
    expect(
      screen.getByText("resource:read, source:read:wm"),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/health/details",
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/auth/me",
        {
          method: "GET",
          headers: expect.any(Headers),
        },
      );
    });
  });

  it("renders auth claims error instead of fake empty auth values", async () => {
    fetchMock = vi.fn().mockImplementation((url) => {
      if (url === "http://localhost:8000/api/v1/health/details") {
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue({
            status: "ok",
            service: "stitch-api",
            runtime: {
              environment: "dev",
              started_at: "2026-04-06T10:00:00Z",
              uptime_seconds: 123.456,
            },
            auth: {
              disabled: false,
              startup_validated: true,
            },
            frontend: {
              origin: "http://localhost:3000",
            },
            database: {
              dialect: "postgresql",
              host: "localhost",
              port: 5432,
              database: "stitch",
              reachable: true,
            },
            build: {
              app_version: "0.1.0",
              build_id: "api-local",
              git_sha: "1234567890abcdef",
              build_time: "2026-04-06T09:59:00Z",
            },
          }),
        });
      }

      if (url === "http://localhost:8000/api/v1/auth/me") {
        return Promise.resolve({
          ok: false,
          json: vi.fn().mockResolvedValue({
            detail: "Invalid or expired token",
          }),
        });
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen />);

    await waitFor(() => {
      expect(screen.getByText("Auth Claims Status")).toBeInTheDocument();
    });

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Auth Claims Error")).toBeInTheDocument();
    expect(screen.getByText("Invalid or expired token")).toBeInTheDocument();
    expect(screen.queryByText("Auth Subject")).not.toBeInTheDocument();
    expect(screen.queryByText("Auth Permissions")).not.toBeInTheDocument();
  });

  it("renders auth claims as not requested when logged out", async () => {
    vi.mocked(useAuth0).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      user: null,
      getAccessTokenSilently,
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    });
    fetchMock = vi.fn().mockImplementation((url) => {
      if (url === "http://localhost:8000/api/v1/health/details") {
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue({
            status: "ok",
            service: "stitch-api",
            runtime: {
              environment: "dev",
              started_at: "2026-04-06T10:00:00Z",
              uptime_seconds: 123.456,
            },
            auth: {
              disabled: false,
              startup_validated: true,
            },
            frontend: {
              origin: "http://localhost:3000",
            },
            database: {
              dialect: "postgresql",
              host: "localhost",
              port: 5432,
              database: "stitch",
              reachable: true,
            },
            build: {
              app_version: "0.1.0",
              build_id: "api-local",
              git_sha: "1234567890abcdef",
              build_time: "2026-04-06T09:59:00Z",
            },
          }),
        });
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen />);

    await waitFor(() => {
      expect(screen.getByText("Auth Claims Status")).toBeInTheDocument();
    });

    expect(screen.getByText("Not requested")).toBeInTheDocument();
    expect(screen.queryByText("Auth Subject")).not.toBeInTheDocument();
    expect(screen.queryByText("Auth Permissions")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/me",
      expect.anything(),
    );
  });

  it("renders API docs link with correct URL", async () => {
    vi.mocked(useAuth0).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      user: null,
      getAccessTokenSilently,
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    });
    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen={false} />);

    const link = screen.getByRole("link", { name: "API docs" });

    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "http://localhost:8000/docs");
  });

  it("renders unavailable state when API docs URL cannot be derived", async () => {
    setConfigForTests({
      ...createMockConfig(),
      apiBaseUrl: "http://localhost:8000",
    });
    vi.mocked(useAuth0).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      user: null,
      getAccessTokenSilently,
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    });
    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen={false} />);

    expect(screen.getByText("API docs unavailable")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "API docs" }),
    ).not.toBeInTheDocument();
  });

  it("copies the diagnostics payload", async () => {
    const { default: ColophonPanel } = await import("./ColophonPanel");

    renderWithQueryClient(<ColophonPanel diagnosticsOpen />);

    await waitFor(() => {
      expect(screen.getByText("stitch-api")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Copied!" }),
      ).toBeInTheDocument();
    });

    expect(clipboardSpy).toHaveBeenCalledTimes(1);

    const copiedText = clipboardSpy.mock.calls[0][0];
    expect(copiedText).toContain("Bearer Token: [redacted - use Copy token]");
    expect(copiedText).toContain("### Frontend Build Info ###");
    expect(copiedText).toContain("API Base URL: http://localhost:8000/api/v1");
    expect(copiedText).toContain("App Version: 0.0.0");
    expect(copiedText).toContain("Git SHA: abcdef1");
    expect(copiedText).toContain("### Backend Diagnostics ###");
    expect(copiedText).toContain("Service: stitch-api");
    expect(copiedText).toContain("DB Reachable: true");
    expect(copiedText).toContain("Auth Subject: auth0|test-user-id");
    expect(copiedText).toContain(
      "Auth Permissions: resource:read, source:read:wm",
    );
    expect(copiedText).toContain("### Runtime Info ###");
    expect(copiedText).toContain("User Agent: VitestBrowser/1.0");
  });
});
