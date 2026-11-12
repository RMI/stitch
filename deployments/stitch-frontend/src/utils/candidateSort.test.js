import { afterEach, describe, expect, it, vi } from "vitest";
import { sortCandidates } from "./candidateSort";

// The API lists candidates newest first; tests use that order as given.
const CANDIDATES = [{ id: 5 }, { id: 4 }, { id: 3 }, { id: 2 }, { id: 1 }];
const ids = (list) => list.map((candidate) => candidate.id);

describe("sortCandidates", () => {
  it("keeps the API's newest-first order for 'newest'", () => {
    expect(ids(sortCandidates(CANDIDATES, "newest"))).toEqual([5, 4, 3, 2, 1]);
  });

  it("reverses it for 'oldest'", () => {
    expect(ids(sortCandidates(CANDIDATES, "oldest"))).toEqual([1, 2, 3, 4, 5]);
  });

  it("does not modify the list it is given", () => {
    const list = [...CANDIDATES];
    sortCandidates(list, "oldest");
    expect(ids(list)).toEqual([5, 4, 3, 2, 1]);
  });

  it("groups by status for 'status': candidates, then denied, then approved, newest first within each", () => {
    const mixed = [
      { id: 6, status: "APPROVED" },
      { id: 5, status: "PENDING" },
      { id: 4, status: "DENIED" },
      { id: 3, status: "APPROVED" },
      { id: 2, status: "PENDING" },
      { id: 1, status: "DENIED" },
    ];
    expect(ids(sortCandidates(mixed, "status"))).toEqual([5, 2, 4, 1, 6, 3]);
  });

  describe("by name", () => {
    const NAMED = [
      { id: 5, display_name: "burgan" },
      { id: 4, display_name: "Ábalos" },
      { id: 3, display_name: "Abbott" },
      { id: 2, display_name: "Burgan" },
      { id: 1, display_name: "Zubair" },
    ];

    // The test runs with an English default language, where base
    // sensitivity ignores case and accents.
    it("sorts A to Z, ignoring case and accents in English", () => {
      // "Ábalos" sorts with "Abalos", before "Abbott".
      expect(ids(sortCandidates(NAMED, "name-asc"))).toEqual([4, 3, 5, 2, 1]);
    });

    it("sorts Z to A", () => {
      expect(ids(sortCandidates(NAMED, "name-desc"))).toEqual([1, 5, 2, 3, 4]);
    });

    it("breaks ties between equal names newest first, in both directions", () => {
      // "burgan" (5) and "Burgan" (2) are equal ignoring case.
      const asc = ids(sortCandidates(NAMED, "name-asc"));
      const desc = ids(sortCandidates(NAMED, "name-desc"));
      expect(asc.indexOf(5)).toBeLessThan(asc.indexOf(2));
      expect(desc.indexOf(5)).toBeLessThan(desc.indexOf(2));
    });
  });
});

describe("sortCandidates in a non-English browser", () => {
  // Names sort the way the reviewer's browser language alphabetizes. In
  // Swedish, "ä" is its own letter sorted after "z", so a Swedish reviewer
  // sees Swedish order rather than English.
  afterEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("follows the browser's language", async () => {
    const RealCollator = Intl.Collator;
    // A regular function, not an arrow, because the code calls it with `new`.
    vi.spyOn(Intl, "Collator").mockImplementation(
      function SwedishDefaultCollator(locales, options) {
        return new RealCollator(locales ?? "sv", options);
      },
    );
    vi.resetModules();
    const { sortCandidates: sortWithSwedishDefault } =
      await import("./candidateSort");

    const sorted = sortWithSwedishDefault(
      [
        { id: 3, display_name: "Zeta" },
        { id: 2, display_name: "Ägir" },
        { id: 1, display_name: "Alpha" },
      ],
      "name-asc",
    );
    // Swedish order: "Ägir" after "Zeta" (in English it would come first).
    expect(sorted.map((candidate) => candidate.id)).toEqual([1, 3, 2]);
  });
});
