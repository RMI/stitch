import { describe, it, expect } from "vitest";
import {
  parseMergeReviewParams,
  toMergeCandidateQuery,
  toMergeReviewParams,
} from "./mergeReviewParams";

const parse = (search) => parseMergeReviewParams(new URLSearchParams(search));
const serialize = (state) => toMergeReviewParams(state).toString();

const DEFAULT_STATE = {
  page: 1,
  pageSize: 25,
  statuses: ["PENDING"],
  sortKey: "newest",
};

describe("parseMergeReviewParams", () => {
  it("returns the pending queue, newest first, for an empty query string", () => {
    expect(parse("")).toEqual(DEFAULT_STATE);
  });

  it("reads every supported param", () => {
    expect(
      parse(
        "page=3&page_size=50&status=DENIED&status=APPROVED&sort_by=reviewed_at&sort_order=asc",
      ),
    ).toEqual({
      page: 3,
      pageSize: 50,
      // Canonical order, whatever order the URL used.
      statuses: ["APPROVED", "DENIED"],
      sortKey: "earliest-reviewed",
    });
  });

  it("reads status=all as every status", () => {
    expect(parse("status=all").statuses).toEqual([]);
  });

  it("drops unknown statuses, falling back to pending when none are left", () => {
    expect(parse("status=MAYBE&status=DENIED").statuses).toEqual(["DENIED"]);
    expect(parse("status=MAYBE").statuses).toEqual(["PENDING"]);
  });

  it("falls back to defaults for malformed page, page_size and sort", () => {
    expect(parse("page=0&page_size=7&sort_by=name&sort_order=asc")).toEqual(
      DEFAULT_STATE,
    );
    expect(parse("page=abc").page).toBe(1);
    // A lone sort_order has no meaning without its sort_by.
    expect(parse("sort_order=asc").sortKey).toBe("newest");
  });
});

describe("toMergeReviewParams", () => {
  it("writes a bare query string for the default view", () => {
    expect(serialize(DEFAULT_STATE)).toBe("");
  });

  it("writes every non-default part in a fixed order", () => {
    expect(
      serialize({
        page: 2,
        pageSize: 10,
        statuses: ["DENIED", "PENDING"],
        sortKey: "oldest",
      }),
    ).toBe(
      "page=2&page_size=10&status=PENDING&status=DENIED&sort_by=created&sort_order=asc",
    );
  });

  it("writes an empty status selection as status=all", () => {
    expect(serialize({ ...DEFAULT_STATE, statuses: [] })).toBe("status=all");
  });

  it("round-trips through parse", () => {
    const state = {
      page: 4,
      pageSize: 100,
      statuses: [],
      sortKey: "recently-reviewed",
    };
    expect(parse(serialize(state))).toEqual(state);
  });
});

describe("toMergeCandidateQuery", () => {
  it("maps the view to the list endpoint's params", () => {
    expect(
      toMergeCandidateQuery({
        page: 2,
        pageSize: 50,
        statuses: ["PENDING", "DENIED"],
        sortKey: "recently-reviewed",
      }),
    ).toEqual({
      page: 2,
      page_size: 50,
      status: ["PENDING", "DENIED"],
      sort_by: "reviewed_at",
      sort_order: "desc",
    });
  });

  it("sends no status filter when every status is wanted", () => {
    expect(
      toMergeCandidateQuery({ ...DEFAULT_STATE, statuses: [] }).status,
    ).toBeUndefined();
  });
});
