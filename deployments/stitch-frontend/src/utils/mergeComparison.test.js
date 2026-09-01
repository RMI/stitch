import { describe, expect, it } from "vitest";
import { isEmptyValue } from "./mergeComparison";

describe("isEmptyValue", () => {
  it("treats null, undefined, and empty string as empty", () => {
    expect(isEmptyValue(null)).toBe(true);
    expect(isEmptyValue(undefined)).toBe(true);
    expect(isEmptyValue("")).toBe(true);
  });

  it("treats populated values as non-empty, including falsy ones", () => {
    expect(isEmptyValue("Burgan")).toBe(false);
    expect(isEmptyValue(0)).toBe(false);
    expect(isEmptyValue(false)).toBe(false);
  });
});
