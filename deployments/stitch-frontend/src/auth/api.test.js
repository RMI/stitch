import { describe, it, expect, vi, beforeEach } from "vitest";
import { createAuthenticatedFetcher } from "./api";

describe("createAuthenticatedFetcher", () => {
  let getAccessTokenSilently;
  let fetcher;

  beforeEach(() => {
    getAccessTokenSilently = vi.fn().mockResolvedValue("test-token");
    fetcher = createAuthenticatedFetcher(getAccessTokenSilently);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))),
    );
  });

  it("attaches Bearer token to request", async () => {
    await fetcher("http://api.test/data");

    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("passes audience to getAccessTokenSilently", async () => {
    await fetcher("http://api.test/data");

    expect(getAccessTokenSilently).toHaveBeenCalledWith({
      authorizationParams: { audience: "https://test-api" },
    });
  });

  it("preserves caller headers", async () => {
    await fetcher("http://api.test/data", {
      headers: { "Content-Type": "application/json" },
    });

    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Content-Type")).toBe("application/json");
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("overrides caller Authorization with token", async () => {
    await fetcher("http://api.test/data", {
      headers: { Authorization: "Bearer old-token" },
    });

    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("propagates token acquisition errors", async () => {
    getAccessTokenSilently.mockRejectedValue(new Error("token error"));
    fetcher = createAuthenticatedFetcher(getAccessTokenSilently);

    await expect(fetcher("http://api.test/data")).rejects.toThrow(
      "token error",
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("propagates fetch errors", async () => {
    fetch.mockRejectedValue(new Error("network error"));

    await expect(fetcher("http://api.test/data")).rejects.toThrow(
      "network error",
    );
  });
});
