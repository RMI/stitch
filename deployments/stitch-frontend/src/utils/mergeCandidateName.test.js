import { describe, expect, it } from "vitest";
import { pickCandidateName } from "./mergeCandidateName";

describe("pickCandidateName", () => {
  it("picks the name from the highest-priority source", () => {
    const details = [
      { data: { name: "Fake Field Alpha" }, provenance: { name: "llm" } },
      { data: { name: "Fake Field Beta" }, provenance: { name: "gem" } },
      { data: { name: "Fake Field Gamma" }, provenance: { name: "rmi" } },
    ];

    expect(pickCandidateName(details)).toBe("Fake Field Gamma");
  });

  it("uses the first resource when the winning source is tied", () => {
    const details = [
      { data: { name: "Burgan" }, provenance: { name: "gem" } },
      { data: { name: "Bergan" }, provenance: { name: "gem" } },
    ];

    expect(pickCandidateName(details)).toBe("Burgan");
  });

  it("skips resources with no name even if their source outranks the rest", () => {
    const details = [
      { data: { name: null }, provenance: { name: "rmi" } },
      { data: { name: "Arabian Field" }, provenance: { name: "wm" } },
    ];

    expect(pickCandidateName(details)).toBe("Arabian Field");
  });

  it("returns null when no resource has a name", () => {
    const details = [
      { data: { name: null }, provenance: { name: "rmi" } },
      { data: { name: "" }, provenance: { name: "gem" } },
    ];

    expect(pickCandidateName(details)).toBeNull();
  });

  it("treats an unrecognized or missing source as lowest priority", () => {
    const details = [
      { data: { name: "Unranked Field" }, provenance: { name: "unknown" } },
      { data: { name: "Known Field" }, provenance: { name: "wm" } },
    ];

    expect(pickCandidateName(details)).toBe("Known Field");
  });

  it("returns null for an empty list", () => {
    expect(pickCandidateName([])).toBeNull();
  });
});
