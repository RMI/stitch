import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const originalFetch = global.fetch;

describe("config/env", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("returns correct config when runtime config is present", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        appEnv: "test",
        apiUrl: "https://example.test/api/v1",
        entityLinkageUrl: "https://entity-linkage.test/api/v1",
        stitchLlmUrl: "https://stitch-llm.test/api/v1",
        etlGemUrl: "https://etl-gem.test/api/v1",
        etlWoodmacUrl: "https://etl-woodmac.test/api/v1",
        auth0Domain: "my.auth0.com",
        auth0ClientId: "my-client-id",
        auth0Audience: "https://my-api",
      }),
    });

    vi.stubEnv("VITE_BUILD_ID", "gha-123");
    vi.stubEnv("VITE_GIT_SHA", "abcdef123");
    vi.stubEnv("VITE_BUILD_TIME", "2026-04-17T10:00:00Z");

    const { loadConfig } = await import("./env.js");
    const config = await loadConfig();

    expect(global.fetch).toHaveBeenCalledWith("/config.json", {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    expect(config.auth0.domain).toBe("my.auth0.com");
    expect(config.auth0.clientId).toBe("my-client-id");
    expect(config.auth0.audience).toBe("https://my-api");
    expect(config.apiBaseUrl).toBe("https://example.test/api/v1");
    expect(config.entityLinkageBaseUrl).toBe(
      "https://entity-linkage.test/api/v1",
    );
    expect(config.stitchLlmBaseUrl).toBe("https://stitch-llm.test/api/v1");
    expect(config.etlGemBaseUrl).toBe("https://etl-gem.test/api/v1");
    expect(config.etlWoodmacBaseUrl).toBe("https://etl-woodmac.test/api/v1");
    expect(config.appEnv).toBe("test");

    expect(config.build.buildId).toBe("gha-123");
    expect(config.build.gitSha).toBe("abcdef123");
    expect(config.build.buildTime).toBe("2026-04-17T10:00:00Z");
    expect(Object.isFrozen(config)).toBe(true);
    expect(Object.isFrozen(config.auth0)).toBe(true);
    expect(Object.isFrozen(config.build)).toBe(true);
  });

  it("throws when required runtime config values are missing", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        appEnv: "test",
        auth0Domain: "",
        auth0ClientId: "",
        auth0Audience: "",
      }),
    });

    const { loadConfig } = await import("./env.js");

    await expect(loadConfig()).rejects.toThrow("auth0Domain");
  });

  it("throws when appEnv is missing", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        auth0Domain: "my.auth0.com",
        auth0ClientId: "my-client-id",
        auth0Audience: "https://my-api",
      }),
    });

    const { loadConfig } = await import("./env.js");

    await expect(loadConfig()).rejects.toThrow("appEnv");
  });

  it("throws when runtime config values have the wrong type", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        appEnv: "test",
        apiUrl: 1234,
        entityLinkageUrl: "https://entity-linkage.test/api/v1",
        auth0Domain: "my.auth0.com",
        auth0ClientId: "my-client-id",
        auth0Audience: "https://my-api",
      }),
    });

    const { loadConfig } = await import("./env.js");

    await expect(loadConfig()).rejects.toThrow(
      'Runtime config value "apiUrl" must be a string.',
    );
  });

  it("uses default API URLs when runtime values are unset", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        appEnv: "local",
        auth0Domain: "my.auth0.com",
        auth0ClientId: "my-client-id",
        auth0Audience: "https://my-api",
        apiUrl: "",
        entityLinkageUrl: "",
        stitchLlmUrl: "",
        etlGemUrl: "",
        etlWoodmacUrl: "",
      }),
    });

    const { loadConfig } = await import("./env.js");
    const config = await loadConfig();

    expect(config.apiBaseUrl).toBe("http://localhost:8000/api/v1");
    expect(config.entityLinkageBaseUrl).toBe("http://localhost:8001/api/v1");
    expect(config.stitchLlmBaseUrl).toBe("http://localhost:8002/api/v1");
    expect(config.etlGemBaseUrl).toBe("http://localhost:8101/api/v1");
    expect(config.etlWoodmacBaseUrl).toBe("http://localhost:8102/api/v1");
  });

  it("throws when config fetch fails", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
    });

    const { loadConfig } = await import("./env.js");

    await expect(loadConfig()).rejects.toThrow(
      "Failed to load runtime config from /config.json: 404 Not Found",
    );
  });
});
