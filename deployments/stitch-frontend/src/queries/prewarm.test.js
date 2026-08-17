import { describe, it, expect, vi, beforeEach } from "vitest";
import { prewarmApi } from "./prewarm";

describe("prewarmApi", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("requests the API health endpoint that also opens a database connection", async () => {
    await prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/health/details",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("sends no headers, so the request stays CORS-simple", async () => {
    await prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1" });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers).toBeUndefined();
  });

  it("does not abort on a timer, so Azure can hold the request while it starts a replica", async () => {
    await prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1" });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.signal).toBeUndefined();
  });

  it("tolerates a trailing slash on the base URL", async () => {
    await prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1/" });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/health/details",
      expect.anything(),
    );
  });

  it("resolves when the request fails, so bootstrap is never blocked", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1" }),
    ).resolves.toBeUndefined();
  });

  it("resolves when the API answers with an error status", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 503 });

    await expect(
      prewarmApi({ apiBaseUrl: "https://api.example.test/api/v1" }),
    ).resolves.toBeUndefined();
  });

  it("does nothing when no API base URL is configured", async () => {
    await expect(prewarmApi({})).resolves.toBeUndefined();
    await expect(prewarmApi(undefined)).resolves.toBeUndefined();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
