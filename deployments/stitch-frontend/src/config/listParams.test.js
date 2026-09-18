import { describe, it, expect } from "vitest";
import { parseListParams, toListParams } from "./listParams";

const parse = (search) => parseListParams(new URLSearchParams(search));
const serialize = (state) => toListParams(state).toString();

const DEFAULT_STATE = {
  page: 1,
  pageSize: 10,
  q: "",
  sortBy: null,
  sortOrder: "asc",
  filters: {
    country: [],
    region: [],
    state_province: [],
    basin: [],
    field_status: [],
    primary_hydrocarbon_group: [],
  },
};

describe("parseListParams", () => {
  it("returns defaults for an empty query string", () => {
    expect(parse("")).toEqual(DEFAULT_STATE);
  });

  it("reads every supported param", () => {
    const state = parse(
      "page=2&page_size=25&q=ghawar&sort_by=name&sort_order=desc&country=NOR&country=SAU",
    );
    expect(state.page).toBe(2);
    expect(state.pageSize).toBe(25);
    expect(state.q).toBe("ghawar");
    expect(state.sortBy).toBe("name");
    expect(state.sortOrder).toBe("desc");
    expect(state.filters.country).toEqual(["NOR", "SAU"]);
  });

  it("trims the search term", () => {
    expect(parse("q=%20%20ghawar%20%20").q).toBe("ghawar");
  });

  it("drops empty filter values", () => {
    expect(parse("country=&country=NOR").filters.country).toEqual(["NOR"]);
  });

  it("ignores params it does not own", () => {
    expect(parse("utm_source=email&page=2").page).toBe(2);
  });

  describe("tolerates junk without throwing", () => {
    it.each([
      ["page=abc", "page", 1],
      ["page=0", "page", 1],
      ["page=-3", "page", 1],
      ["page=1.5", "page", 1],
      ["page=1e21", "page", 1],
      ["page=1e3", "page", 1],
      ["page_size=7", "pageSize", 10],
      ["page_size=abc", "pageSize", 10],
    ])("%s falls back to the default", (search, key, expected) => {
      expect(parse(search)[key]).toBe(expected);
    });

    it("drops an unsortable sort_by", () => {
      const state = parse("sort_by=bogus&sort_order=desc");
      expect(state.sortBy).toBeNull();
    });

    it("drops sort_order when sort_by is absent", () => {
      expect(parse("sort_order=desc").sortBy).toBeNull();
    });

    it("falls back to asc for an unknown sort_order", () => {
      const state = parse("sort_by=name&sort_order=sideways");
      expect(state.sortBy).toBe("name");
      expect(state.sortOrder).toBe("asc");
    });
  });
});

describe("toListParams", () => {
  it("omits every default, so the default view is a bare URL", () => {
    expect(serialize(DEFAULT_STATE)).toBe("");
  });

  it("serializes in a fixed order", () => {
    const params = serialize({
      ...DEFAULT_STATE,
      page: 2,
      pageSize: 25,
      q: "ghawar",
      sortBy: "name",
      sortOrder: "desc",
      filters: { ...DEFAULT_STATE.filters, country: ["NOR", "SAU"] },
    });
    expect(decodeURIComponent(params)).toBe(
      "page=2&page_size=25&q=ghawar&sort_by=name&sort_order=desc&country=NOR&country=SAU",
    );
  });

  it("omits sort_order when nothing is sorted", () => {
    expect(serialize({ ...DEFAULT_STATE, sortOrder: "desc" })).toBe("");
  });

  it("round-trips any state back to itself", () => {
    const state = {
      ...DEFAULT_STATE,
      page: 3,
      pageSize: 50,
      q: "burgan",
      sortBy: "country",
      sortOrder: "desc",
      filters: {
        ...DEFAULT_STATE.filters,
        country: ["NOR"],
        basin: ["Arabian", "Permian"],
      },
    };
    expect(parseListParams(toListParams(state))).toEqual(state);
  });
});
