import { describe, expect, it } from "vitest";
import {
  DEFAULT_HIDDEN_STATUSES,
  MERGE_CANDIDATE_STATUS,
  getStatusClasses,
  getStatusLabel,
} from "./mergeCandidateStatus";

describe("merge candidate status constants", () => {
  it("mirrors the backend's three review states", () => {
    expect(MERGE_CANDIDATE_STATUS).toEqual({
      PENDING: "PENDING",
      APPROVED: "APPROVED",
      DENIED: "DENIED",
    });
  });

  it("hides both terminal states by default, and never PENDING", () => {
    expect(DEFAULT_HIDDEN_STATUSES).toEqual(["APPROVED", "DENIED"]);
    expect(DEFAULT_HIDDEN_STATUSES).not.toContain(
      MERGE_CANDIDATE_STATUS.PENDING,
    );
  });

  it("names every hidden status as a known state", () => {
    for (const status of DEFAULT_HIDDEN_STATUSES) {
      expect(Object.values(MERGE_CANDIDATE_STATUS)).toContain(status);
    }
  });
});

describe("getStatusLabel", () => {
  it('reads PENDING as "CANDIDATE"', () => {
    expect(getStatusLabel(MERGE_CANDIDATE_STATUS.PENDING)).toBe("CANDIDATE");
  });

  it("passes the terminal states through unchanged", () => {
    expect(getStatusLabel(MERGE_CANDIDATE_STATUS.APPROVED)).toBe("APPROVED");
    expect(getStatusLabel(MERGE_CANDIDATE_STATUS.DENIED)).toBe("DENIED");
  });

  it("passes an unrecognized status through rather than blanking it", () => {
    expect(getStatusLabel("NEEDS_INFO")).toBe("NEEDS_INFO");
  });
});

describe("getStatusClasses", () => {
  it("gives each known status its own classes", () => {
    const classes = Object.values(MERGE_CANDIDATE_STATUS).map(getStatusClasses);
    expect(new Set(classes).size).toBe(classes.length);
  });

  it("falls back to neutral classes for an unrecognized status", () => {
    expect(getStatusClasses("NEEDS_INFO")).toBe(
      "border-line bg-surface text-ink",
    );
    expect(getStatusClasses(undefined)).toBe("border-line bg-surface text-ink");
  });
});
