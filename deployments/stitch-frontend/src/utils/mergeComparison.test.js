import { describe, expect, it } from "vitest";
import { getRowStatus } from "./mergeComparison";

describe("getRowStatus", () => {
  it("returns match when all values are populated and identical", () => {
    expect(getRowStatus(["Burgan", "Burgan"])).toBe("match");
  });

  it("returns differs when populated values disagree", () => {
    expect(getRowStatus(["Burgan", "Bergan"])).toBe("differs");
  });

  it("returns match when strings are identical except for case", () => {
    expect(getRowStatus(["Kuwait", "kuwait"])).toBe("match");
    expect(getRowStatus(["KUWAIT", "Kuwait", "kuwait"])).toBe("match");
  });

  it("compares exactly: number and numeric string differ", () => {
    expect(getRowStatus([1938, "1938"])).toBe("differs");
  });

  it("returns differs when only some values are populated", () => {
    expect(getRowStatus(["Arabian", null])).toBe("differs");
    expect(getRowStatus(["Arabian", undefined])).toBe("differs");
    expect(getRowStatus(["Arabian", ""])).toBe("differs");
  });

  it("returns empty when no values are populated", () => {
    expect(getRowStatus([null, undefined, ""])).toBe("empty");
  });

  it("handles three matching sources", () => {
    expect(getRowStatus(["Burgan", "Burgan", "Burgan"])).toBe("match");
  });

  it("handles three sources where one differs", () => {
    expect(getRowStatus(["Burgan", "Burgan", "Safaniya"])).toBe("differs");
  });
});
