import { describe, it, expect, vi, beforeEach } from "vitest";
import { createLLMSuggestion, getResources, getResource } from "./api";

describe("API Functions", () => {
  let mockFetcher;
  let config;

  beforeEach(() => {
    mockFetcher = vi.fn();
    config = {
      apiBaseUrl: "http://localhost:8000/api/v1",
      stitchLlmBaseUrl: "http://localhost:8002/api/v1",
    };
  });

  describe("getResources", () => {
    it("fetches and returns resources successfully", async () => {
      const mockResources = [
        { id: 1, name: "Resource 1", type: "test" },
        { id: 2, name: "Resource 2", type: "test" },
      ];

      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResources,
      });

      const result = await getResources(config, mockFetcher);

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/resources/?page=1&page_size=50",
      );
      expect(result).toEqual(mockResources);
    });

    it("appends filter values as repeated query params", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      await getResources(config, mockFetcher, "resources", {
        filters: { basin: ["Arabian", "Permian"], region: ["Middle East"] },
      });

      const calledUrl = mockFetcher.mock.calls[0][0];
      const url = new URL(calledUrl);
      expect(url.searchParams.getAll("basin")).toEqual(["Arabian", "Permian"]);
      expect(url.searchParams.getAll("region")).toEqual(["Middle East"]);
    });

    it("appends sort_by and sort_order to the URL", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      await getResources(config, mockFetcher, "resources", {
        sort_by: "basin",
        sort_order: "desc",
      });

      const calledUrl = mockFetcher.mock.calls[0][0];
      const url = new URL(calledUrl);
      expect(url.searchParams.get("sort_by")).toBe("basin");
      expect(url.searchParams.get("sort_order")).toBe("desc");
    });

    it("appends q to the URL when provided", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      await getResources(config, mockFetcher, "resources", {
        q: "ghawar",
      });

      const calledUrl = mockFetcher.mock.calls[0][0];
      const url = new URL(calledUrl);
      expect(url.searchParams.get("q")).toBe("ghawar");
    });

    it("omits sort params when not provided", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      await getResources(config, mockFetcher);

      const calledUrl = mockFetcher.mock.calls[0][0];
      const url = new URL(calledUrl);
      expect(url.searchParams.has("sort_by")).toBe(false);
      expect(url.searchParams.has("sort_order")).toBe(false);
    });

    it("throws error when response is not ok", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(getResources(config, mockFetcher)).rejects.toThrow(
        "HTTP error! status: 500",
      );
    });

    it("throws error on network failure", async () => {
      mockFetcher.mockRejectedValueOnce(new Error("Network error"));

      await expect(getResources(config, mockFetcher)).rejects.toThrow(
        "Network error",
      );
    });
  });

  describe("getResource", () => {
    it("fetches and returns a single resource successfully", async () => {
      const mockResource = { id: 42, name: "Test Resource", type: "example" };

      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResource,
      });

      const result = await getResource(config, 42, mockFetcher);

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/resources/42",
      );
      expect(result).toEqual(mockResource);
    });

    it("throws error with status when response is not ok", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      try {
        await getResource(config, 999, mockFetcher);
        expect.fail("Should have thrown an error");
      } catch (error) {
        expect(error.message).toBe("HTTP error! status: 404");
        expect(error.status).toBe(404);
      }
    });

    it("includes status code in error object for 404", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(getResource(config, 123, mockFetcher)).rejects.toMatchObject(
        {
          message: "HTTP error! status: 404",
          status: 404,
        },
      );
    });

    it("includes status code in error object for 500", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(getResource(config, 1, mockFetcher)).rejects.toMatchObject({
        message: "HTTP error! status: 500",
        status: 500,
      });
    });

    it("throws error on network failure", async () => {
      mockFetcher.mockRejectedValueOnce(new Error("Failed to fetch"));

      await expect(getResource(config, 1, mockFetcher)).rejects.toThrow(
        "Failed to fetch",
      );
    });
  });

  describe("createLLMSuggestion", () => {
    it("calls the stitch-llm GET endpoint with the requested field", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          resource_id: 42,
          field: "basin",
          value: "Songliao Basin",
          citations: [],
          query_succeeded: true,
          model: "test-model",
          foundry_request: {},
          foundry_response: {},
        }),
      });

      const result = await createLLMSuggestion(
        config,
        42,
        "basin",
        mockFetcher,
        "oil-gas-fields",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        new URL("http://localhost:8002/api/v1/oil-gas-fields/42?field=basin"),
        { method: "GET" },
      );
      expect(result.value).toBe("Songliao Basin");
    });
  });
});
