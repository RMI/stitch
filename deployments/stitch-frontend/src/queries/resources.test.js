import { describe, it, expect } from "vitest";
import { keepPreviousData } from "@tanstack/react-query";
import { resourceQueries } from "./resources";

const config = { apiBaseUrl: "http://localhost:8000/api/v1" };

describe("resourceQueries.list", () => {
  it("keeps previous page data visible while a new page/filter/sort fetches", () => {
    const query = resourceQueries.list(config, "resources", 1, 10, {});

    expect(query.placeholderData).toBe(keepPreviousData);
  });
});

// Mutations invalidate an entire endpoint's cache with a single-segment
// queryKey ([endpoint]), relying on every real query key being prefixed by
// it. This guards that invariant: break it here and invalidation silently
// stops reaching whichever factory's key no longer starts with [endpoint].
describe("resourceQueries key prefixes", () => {
  const endpoint = "oil-gas-fields";
  const cases = [
    ["list", () => resourceQueries.list(config, endpoint, 1, 10, {})],
    [
      "filterOptions",
      () => resourceQueries.filterOptions(config, endpoint, "basin"),
    ],
    ["detail", () => resourceQueries.detail(config, endpoint, 42)],
    [
      "fieldSources",
      () => resourceQueries.fieldSources(config, endpoint, 42, "basin"),
    ],
    ["view", () => resourceQueries.view(config, endpoint, 42)],
    [
      "mergeCandidates",
      () => resourceQueries.mergeCandidates(config, endpoint),
    ],
    [
      "mergeCandidate",
      () => resourceQueries.mergeCandidate(config, endpoint, 7),
    ],
  ];

  it.each(cases)("%s's queryKey is prefixed by [endpoint]", (_name, build) => {
    expect(build().queryKey[0]).toBe(endpoint);
  });
});
