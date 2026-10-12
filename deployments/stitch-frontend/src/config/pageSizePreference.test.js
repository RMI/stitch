import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PAGE_SIZE_STORAGE_KEY,
  getRememberedPageSize,
  rememberPageSize,
} from "./pageSizePreference";

afterEach(() => {
  window.sessionStorage.clear();
});

describe("pageSizePreference", () => {
  it("remembers nothing until a page size is chosen", () => {
    expect(getRememberedPageSize()).toBeNull();
  });

  it("returns the page size it was given", () => {
    rememberPageSize(50);
    expect(getRememberedPageSize()).toBe(50);
    expect(window.sessionStorage.getItem(PAGE_SIZE_STORAGE_KEY)).toBe("50");
  });

  it.each([["7"], ["abc"], [""], ["1000"]])(
    "ignores a stored value that is not an offered page size (%j)",
    (stored) => {
      window.sessionStorage.setItem(PAGE_SIZE_STORAGE_KEY, stored);
      expect(getRememberedPageSize()).toBeNull();
    },
  );

  it("does not store a page size that is not offered", () => {
    rememberPageSize(7);
    expect(window.sessionStorage.getItem(PAGE_SIZE_STORAGE_KEY)).toBeNull();
  });

  it("treats unavailable storage as nothing remembered, without throwing", () => {
    // Some privacy modes make session storage throw on every access.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    expect(() => rememberPageSize(50)).not.toThrow();
    expect(getRememberedPageSize()).toBeNull();
  });
});
