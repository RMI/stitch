import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "../config/context-provider";
import { getConfig } from "../config/env";
import * as apiModule from "../queries/api";
import {
  useCreateSourceForResource,
  useReviewMergeCandidate,
  useResource,
  useResourceDetail,
} from "./useResources";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function wrapper({ children }) {
    return (
      <ConfigProvider config={getConfig()}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </ConfigProvider>
    );
  }
  return { wrapper, queryClient };
}

describe("useCreateSourceForResource", () => {
  it("creates the source through the API and returns it", async () => {
    const createSpy = vi
      .spyOn(apiModule, "createSourceForResource")
      .mockResolvedValue({ id: 99, source: "rmi" });
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCreateSourceForResource("oil-gas-fields"),
      { wrapper },
    );

    let created;
    await act(async () => {
      created = await result.current.mutateAsync({
        resourceId: 42,
        payload: { source: "rmi", basin: "Deep Basin" },
      });
    });

    expect(created).toEqual({ id: 99, source: "rmi" });
    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({ apiBaseUrl: "http://localhost:8000/api/v1" }),
      42,
      { source: "rmi", basin: "Deep Basin" },
      expect.any(Function),
      "oil-gas-fields",
    );
  });

  it("invalidates every query for the endpoint after a successful create", async () => {
    vi.spyOn(apiModule, "createSourceForResource").mockResolvedValue({
      id: 99,
    });
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useCreateSourceForResource("oil-gas-fields"),
      { wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({ resourceId: 42, payload: {} });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["oil-gas-fields"],
    });
  });

  it("does not invalidate any queries when the create fails", async () => {
    vi.spyOn(apiModule, "createSourceForResource").mockRejectedValue(
      new Error("create failed"),
    );
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useCreateSourceForResource("oil-gas-fields"),
      { wrapper },
    );

    await act(async () => {
      await expect(
        result.current.mutateAsync({ resourceId: 42, payload: {} }),
      ).rejects.toThrow("create failed");
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

describe("read-hook enabled defaults", () => {
  it("useResource fetches automatically once a valid id is given, with no explicit enabled arg", async () => {
    const getResourceSpy = vi
      .spyOn(apiModule, "getResource")
      .mockResolvedValue({ id: 42 });
    const { wrapper } = createWrapper();

    renderHook(() => useResource("oil-gas-fields", 42), { wrapper });

    await vi.waitFor(() => expect(getResourceSpy).toHaveBeenCalled());
  });

  it("useResource does not fetch when id is null, with no explicit enabled arg", async () => {
    const getResourceSpy = vi.spyOn(apiModule, "getResource");
    const { wrapper } = createWrapper();

    renderHook(() => useResource("oil-gas-fields", null), { wrapper });

    // Give any wrongly-scheduled fetch a chance to fire before asserting.
    await act(async () => {});
    expect(getResourceSpy).not.toHaveBeenCalled();
  });

  it("useResourceDetail does not fetch when id is null, with no explicit enabled arg", async () => {
    const getResourceDetailSpy = vi.spyOn(apiModule, "getResourceDetail");
    const { wrapper } = createWrapper();

    renderHook(() => useResourceDetail("oil-gas-fields", null), { wrapper });

    await act(async () => {});
    expect(getResourceDetailSpy).not.toHaveBeenCalled();
  });
});

describe("useReviewMergeCandidate", () => {
  it("reviews the candidate through the API and returns the result", async () => {
    const reviewSpy = vi
      .spyOn(apiModule, "reviewMergeCandidate")
      .mockResolvedValue({ id: 7, status: "APPROVED" });
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useReviewMergeCandidate("oil-gas-fields"),
      { wrapper },
    );

    let reviewed;
    await act(async () => {
      reviewed = await result.current.mutateAsync({
        id: 7,
        action: "approve",
        reviewNotes: "looks right",
      });
    });

    expect(reviewed).toEqual({ id: 7, status: "APPROVED" });
    expect(reviewSpy).toHaveBeenCalledWith(
      expect.objectContaining({ apiBaseUrl: "http://localhost:8000/api/v1" }),
      7,
      "approve",
      expect.any(Function),
      "oil-gas-fields",
      "looks right",
    );
  });

  it("invalidates every query for the endpoint after a successful review", async () => {
    vi.spyOn(apiModule, "reviewMergeCandidate").mockResolvedValue({
      id: 7,
      status: "APPROVED",
    });
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useReviewMergeCandidate("oil-gas-fields"),
      { wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({
        id: 7,
        action: "approve",
        reviewNotes: "",
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["oil-gas-fields"],
    });
  });
});
