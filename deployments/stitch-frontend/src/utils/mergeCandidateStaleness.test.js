import { describe, expect, it } from "vitest";
import { readCandidateStaleness } from "./mergeCandidateStaleness";

describe("readCandidateStaleness", () => {
  it("reports the moves and isStale when repointed_resources is non-empty", () => {
    const { isStale, moves } = readCandidateStaleness({
      repointed_resources: [{ resource_id: 102, repointed_to: 301 }],
    });
    expect(isStale).toBe(true);
    expect(moves).toEqual([{ resource_id: 102, repointed_to: 301 }]);
  });

  it("is not stale when repointed_resources is an empty list", () => {
    const { isStale, moves } = readCandidateStaleness({
      repointed_resources: [],
    });
    expect(isStale).toBe(false);
    expect(moves).toEqual([]);
  });

  it("degrades to not-stale when the field is absent", () => {
    expect(readCandidateStaleness({})).toEqual({ isStale: false, moves: [] });
  });

  it("degrades to not-stale for a null or undefined candidate", () => {
    expect(readCandidateStaleness(undefined)).toEqual({
      isStale: false,
      moves: [],
    });
    expect(readCandidateStaleness(null)).toEqual({ isStale: false, moves: [] });
  });

  it("ignores a non-array repointed_resources", () => {
    expect(readCandidateStaleness({ repointed_resources: "nope" })).toEqual({
      isStale: false,
      moves: [],
    });
  });
});
