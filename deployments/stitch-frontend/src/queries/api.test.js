import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  createMergeCandidate,
  createResource,
  getLLMSuggestionStatus,
  getResourceFilterOptions,
  getResources,
  getResource,
  reviewMergeCandidate,
  startLLMSuggestion,
} from "./api";

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

  describe("getResourceFilterOptions", () => {
    it("fetches and returns filter options successfully", async () => {
      const mockOptions = { field: "basin", values: ["Arabian", "Permian"] };

      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockOptions,
      });

      const result = await getResourceFilterOptions(
        config,
        mockFetcher,
        "oil-gas-fields",
        "basin",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/oil-gas-fields/filter-options?field=basin",
      );
      expect(result).toEqual(mockOptions);
    });

    it("throws error when filter options response is not ok", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(
        getResourceFilterOptions(
          config,
          mockFetcher,
          "oil-gas-fields",
          "basin",
        ),
      ).rejects.toThrow("HTTP error! status: 500");
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

  describe("startLLMSuggestion", () => {
    it("POSTs resource_id/field/force to the stitch-llm start endpoint", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 202,
        json: async () => ({ job_id: "job-1", state: "running", result: null }),
      });

      const record = await startLLMSuggestion(
        config,
        { resourceId: 42, field: "basin", force: true },
        mockFetcher,
        "oil-gas-fields",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8002/api/v1/oil-gas-fields/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resource_id: 42,
            field: "basin",
            force: true,
          }),
        },
      );
      expect(record.job_id).toBe("job-1");
    });

    it("surfaces structured JSON detail and status on failure", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 403,
        text: async () => JSON.stringify({ detail: "missing permission" }),
      });

      await expect(
        startLLMSuggestion(
          config,
          { resourceId: 42, field: "basin" },
          mockFetcher,
          "oil-gas-fields",
        ),
      ).rejects.toMatchObject({
        message: "missing permission",
        status: 403,
      });
    });
  });

  describe("getLLMSuggestionStatus", () => {
    it("GETs the status endpoint for a job id", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          job_id: "job-1",
          state: "succeeded",
          result: { field: "basin", value: "Songliao Basin" },
        }),
      });

      const record = await getLLMSuggestionStatus(
        config,
        "job-1",
        mockFetcher,
        "oil-gas-fields",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8002/api/v1/oil-gas-fields/status/job-1",
        { method: "GET" },
      );
      expect(record.result.value).toBe("Songliao Basin");
    });
  });

  describe("createResource", () => {
    it("posts the resource payload to the Stitch API", async () => {
      const payload = { source_data: [{ source: "llm" }] };
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 123 }),
      });

      const result = await createResource(
        config,
        payload,
        mockFetcher,
        "oil-gas-fields",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/oil-gas-fields/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      expect(result).toEqual({ id: 123 });
    });

    it("stringifies structured validation errors from the API", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 422,
        text: async () =>
          JSON.stringify({
            detail: [
              {
                loc: ["body", "source_data", 0, "llm", "name"],
                msg: "Field required",
              },
            ],
          }),
      });

      await expect(
        createResource(
          config,
          { source_data: [] },
          mockFetcher,
          "oil-gas-fields",
        ),
      ).rejects.toMatchObject({
        message: JSON.stringify(
          [
            {
              loc: ["body", "source_data", 0, "llm", "name"],
              msg: "Field required",
            },
          ],
          null,
          2,
        ),
        status: 422,
      });
    });
  });

  describe("createMergeCandidate", () => {
    it("posts the resource ids to create a merge candidate", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 88, resource_ids: [42, 123] }),
      });

      const result = await createMergeCandidate(
        config,
        [42, 123],
        mockFetcher,
        "oil-gas-fields",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/oil-gas-fields/merge-candidates",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resource_ids: [42, 123] }),
        },
      );
      expect(result).toEqual({ id: 88, resource_ids: [42, 123] });
    });

    it("surfaces API error detail and status for failed merge creation", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 409,
        text: async () =>
          JSON.stringify({
            detail: { message: "Merge candidate already exists" },
          }),
      });

      await expect(
        createMergeCandidate(config, [42, 123], mockFetcher, "oil-gas-fields"),
      ).rejects.toMatchObject({
        message: JSON.stringify(
          { message: "Merge candidate already exists" },
          null,
          2,
        ),
        status: 409,
      });
    });
  });

  describe("reviewMergeCandidate", () => {
    it("posts the requested review action and notes", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 88, status: "approved" }),
      });

      const result = await reviewMergeCandidate(
        config,
        88,
        "approve",
        mockFetcher,
        "oil-gas-fields",
        "Looks good",
      );

      expect(mockFetcher).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/oil-gas-fields/merge-candidates/88/approve",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ review_notes: "Looks good" }),
        },
      );
      expect(result).toEqual({ id: 88, status: "approved" });
    });

    it("surfaces structured API error detail and status on failure", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 409,
        text: async () =>
          JSON.stringify({
            detail: { message: "Merge candidate already reviewed" },
          }),
      });

      await expect(
        reviewMergeCandidate(
          config,
          88,
          "approve",
          mockFetcher,
          "oil-gas-fields",
        ),
      ).rejects.toMatchObject({
        message: JSON.stringify(
          { message: "Merge candidate already reviewed" },
          null,
          2,
        ),
        status: 409,
      });
    });

    it("falls back to status text when the error body is empty", async () => {
      mockFetcher.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        text: async () => "",
      });

      await expect(
        reviewMergeCandidate(
          config,
          88,
          "approve",
          mockFetcher,
          "oil-gas-fields",
        ),
      ).rejects.toMatchObject({
        message: "Internal Server Error",
        status: 500,
      });
    });
  });
});
