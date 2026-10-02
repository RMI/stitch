import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_MERGE_REVIEW_SORT,
  MERGE_REVIEW_SORT_OPTIONS,
  MERGE_REVIEW_SORT_STORAGE_KEY,
  getRememberedMergeReviewSort,
  rememberMergeReviewSort,
} from "./mergeReviewSortPreference";

afterEach(() => {
  window.sessionStorage.clear();
});

describe("mergeReviewSortPreference", () => {
  it("offers newest, oldest, both name orders and status, newest first by default", () => {
    expect(MERGE_REVIEW_SORT_OPTIONS.map((o) => o.value)).toEqual([
      "newest",
      "oldest",
      "name-asc",
      "name-desc",
      "status",
    ]);
    expect(DEFAULT_MERGE_REVIEW_SORT).toBe("newest");
  });

  it("falls back to the default when nothing is remembered", () => {
    expect(getRememberedMergeReviewSort()).toBe("newest");
  });

  it("returns the sort it was given", () => {
    rememberMergeReviewSort("name-desc");
    expect(getRememberedMergeReviewSort()).toBe("name-desc");
  });

  it("ignores a stored value that is not an offered sort", () => {
    window.sessionStorage.setItem(MERGE_REVIEW_SORT_STORAGE_KEY, "random");
    expect(getRememberedMergeReviewSort()).toBe("newest");
  });

  it("does not store a sort that is not offered", () => {
    rememberMergeReviewSort("random");
    expect(
      window.sessionStorage.getItem(MERGE_REVIEW_SORT_STORAGE_KEY),
    ).toBeNull();
  });

  it("falls back to the default when storage is unavailable, without throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    expect(() => rememberMergeReviewSort("name-asc")).not.toThrow();
    expect(getRememberedMergeReviewSort()).toBe("newest");
  });
});
