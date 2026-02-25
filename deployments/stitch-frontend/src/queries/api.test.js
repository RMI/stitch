import { describe, it, expect, vi, beforeEach } from "vitest";
import { getResources, getResource } from "./api";

describe("API Functions", () => {
  let mockFetcher;

  beforeEach(() => {
    mockFetcher = vi.fn();
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

      const result = await getResources(mockFetcher);

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/resources/",
      );
      expect(result).toEqual(mockResources);
    });

    it("throws error when response is not ok", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(getResources(mockFetcher)).rejects.toThrow(
        "HTTP error! status: 500",
      );
    });

    it("throws error on network failure", async () => {
      mockFetcher.mockRejectedValueOnce(new Error("Network error"));

      await expect(getResources(mockFetcher)).rejects.toThrow("Network error");
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

      const result = await getResource(42, mockFetcher);

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
        await getResource(999, mockFetcher);
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

      await expect(getResource(123, mockFetcher)).rejects.toMatchObject({
        message: "HTTP error! status: 404",
        status: 404,
      });
    });

    it("includes status code in error object for 500", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(getResource(1, mockFetcher)).rejects.toMatchObject({
        message: "HTTP error! status: 500",
        status: 500,
      });
    });

    it("throws error on network failure", async () => {
      mockFetcher.mockRejectedValueOnce(new Error("Failed to fetch"));

      await expect(getResource(1, mockFetcher)).rejects.toThrow(
        "Failed to fetch",
      );
    });
  });
});
