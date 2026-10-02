import { afterEach, describe, expect, it, vi } from "vitest";
import { sortCandidates } from "./candidateSort";

// The API lists candidates newest first; tests use that order as given.
const CANDIDATES = [{ id: 5 }, { id: 4 }, { id: 3 }, { id: 2 }, { id: 1 }];
const ids = (list) => list.map((candidate) => candidate.id);

describe("sortCandidates", () => {
  it("keeps the API's newest-first order for 'newest'", () => {
    expect(ids(sortCandidates(CANDIDATES, "newest", new Map()))).toEqual([
      5, 4, 3, 2, 1,
    ]);
  });

  it("reverses it for 'oldest'", () => {
    expect(ids(sortCandidates(CANDIDATES, "oldest", new Map()))).toEqual([
      1, 2, 3, 4, 5,
    ]);
  });

  it("does not modify the list it is given", () => {
    const list = [...CANDIDATES];
    sortCandidates(list, "oldest", new Map());
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
    expect(ids(sortCandidates(mixed, "status", new Map()))).toEqual([
      5, 2, 4, 1, 6, 3,
    ]);
  });

  describe("by name", () => {
    const names = new Map([
      [5, "burgan"],
      [4, "Ábalos"],
      [3, "Abbott"],
      [2, "Burgan"],
      [1, "Zubair"],
    ]);

    // The test runs with an English default language, where base
    // sensitivity ignores case and accents.
    it("sorts A to Z, ignoring case and accents in English", () => {
      // "Ábalos" sorts with "Abalos", before "Abbott".
      expect(ids(sortCandidates(CANDIDATES, "name-asc", names))).toEqual([
        4, 3, 5, 2, 1,
      ]);
    });

    it("sorts Z to A", () => {
      expect(ids(sortCandidates(CANDIDATES, "name-desc", names))).toEqual([
        1, 5, 2, 3, 4,
      ]);
    });

    it("breaks ties between equal names newest first, in both directions", () => {
      // "burgan" (5) and "Burgan" (2) are equal ignoring case.
      const asc = ids(sortCandidates(CANDIDATES, "name-asc", names));
      const desc = ids(sortCandidates(CANDIDATES, "name-desc", names));
      expect(asc.indexOf(5)).toBeLessThan(asc.indexOf(2));
      expect(desc.indexOf(5)).toBeLessThan(desc.indexOf(2));
    });

    it("puts candidates whose names have not loaded at the end, newest first", () => {
      const partial = new Map([
        [3, "Zubair"],
        [1, "Abbott"],
      ]);
      expect(ids(sortCandidates(CANDIDATES, "name-asc", partial))).toEqual([
        1, 3, 5, 4, 2,
      ]);
      expect(ids(sortCandidates(CANDIDATES, "name-desc", partial))).toEqual([
        3, 1, 5, 4, 2,
      ]);
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

    const names = new Map([
      [3, "Zeta"],
      [2, "Ägir"],
      [1, "Alpha"],
    ]);
    const sorted = sortWithSwedishDefault(
      [{ id: 3 }, { id: 2 }, { id: 1 }],
      "name-asc",
      names,
    );
    // Swedish order: "Ägir" after "Zeta" (in English it would come first).
    expect(sorted.map((candidate) => candidate.id)).toEqual([1, 3, 2]);
  });
});
