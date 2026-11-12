import { describe, expect, it } from "vitest";
import { sortCandidates } from "./candidateSort";

// The API lists candidates newest first; tests use that order as given.
const CANDIDATES = [
  { id: 6, status: "APPROVED" },
  { id: 5, status: "PENDING" },
  { id: 4, status: "DENIED" },
  { id: 3, status: "APPROVED" },
  { id: 2, status: "PENDING" },
  { id: 1, status: "DENIED" },
];
const ids = (list) => list.map((candidate) => candidate.id);

describe("sortCandidates", () => {
  it("keeps the API's order for sorts the API applied", () => {
    for (const sort of ["newest", "oldest", "name-asc"]) {
      expect(ids(sortCandidates(CANDIDATES, sort))).toEqual([6, 5, 4, 3, 2, 1]);
    }
  });

  it("groups by status for 'status': candidates, then denied, then approved, newest first within each", () => {
    expect(ids(sortCandidates(CANDIDATES, "status"))).toEqual([
      5, 2, 4, 1, 6, 3,
    ]);
  });

  it("does not modify the list it is given", () => {
    const list = [...CANDIDATES];
    sortCandidates(list, "status");
    expect(ids(list)).toEqual([6, 5, 4, 3, 2, 1]);
  });
});
