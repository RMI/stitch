import { describe, it, expect } from "vitest";
import { keepPreviousData } from "@tanstack/react-query";
import { resourceQueries } from "./resources";

describe("resourceQueries.list", () => {
  it("keeps previous page data visible while a new page/filter/sort fetches", () => {
    const config = { apiBaseUrl: "http://localhost:8000/api/v1" };

    const query = resourceQueries.list(config, "resources", 1, 10, {});

    expect(query.placeholderData).toBe(keepPreviousData);
  });
});
