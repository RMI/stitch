import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDebouncedValue, DEFAULT_DEBOUNCE_MS } from "./useDebouncedValue";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns the initial value immediately", () => {
    const { result } = renderHook(() => useDebouncedValue("a"));

    expect(result.current).toBe("a");
  });

  it("waits for the delay before returning a new value", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    act(() => vi.advanceTimersByTime(DEFAULT_DEBOUNCE_MS - 1));
    expect(result.current).toBe("a");

    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe("b");
  });

  it("only returns the last value after rapid changes settle", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    act(() => vi.advanceTimersByTime(200));
    rerender({ value: "c" });
    act(() => vi.advanceTimersByTime(200));
    rerender({ value: "d" });

    // 400ms since the first change, but only 0ms since the last one.
    expect(result.current).toBe("a");

    act(() => vi.advanceTimersByTime(DEFAULT_DEBOUNCE_MS));
    expect(result.current).toBe("d");
  });

  it("honors a custom delay", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 1000),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    act(() => vi.advanceTimersByTime(999));
    expect(result.current).toBe("a");

    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe("b");
  });

  it("cancels the pending update on unmount", () => {
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
    const { rerender, unmount } = renderHook(
      ({ value }) => useDebouncedValue(value),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
