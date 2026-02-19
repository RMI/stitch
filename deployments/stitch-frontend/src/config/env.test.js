import { describe, it, expect, vi, beforeEach } from "vitest";

describe("config/env", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("returns correct config when all vars are present", async () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "my.auth0.com");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "my-client-id");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "https://my-api");
    vi.stubEnv("VITE_API_URL", "http://localhost:9000/api/v1");

    const { default: config } = await import("./env.js");

    expect(config.auth0.domain).toBe("my.auth0.com");
    expect(config.auth0.clientId).toBe("my-client-id");
    expect(config.auth0.audience).toBe("https://my-api");
    expect(config.apiBaseUrl).toBe("http://localhost:9000/api/v1");
  });

  it("throws when required vars are missing", async () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "");

    await expect(() => import("./env.js")).rejects.toThrow(
      "VITE_AUTH0_DOMAIN",
    );
  });

  it("uses default API URL when VITE_API_URL is unset", async () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "my.auth0.com");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "my-client-id");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "https://my-api");
    vi.stubEnv("VITE_API_URL", "");

    const { default: config } = await import("./env.js");

    expect(config.apiBaseUrl).toBe("http://localhost:8000/api/v1");
  });
});
