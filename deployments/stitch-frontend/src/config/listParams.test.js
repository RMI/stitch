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

  it("passes unknown filter values through rather than dropping them", () => {
    // Deliberate: which values are valid is server-side data this module cannot
    // see, so guessing here would mean duplicating the API's enums. An unknown
    // free-text value matches nothing; an unknown enum value is the API's 422 to
    // raise. See the module docstring.
    expect(parse("country=ZZ9").filters.country).toEqual(["ZZ9"]);
    expect(parse("field_status=NotAStatus").filters.field_status).toEqual([
      "NotAStatus",
    ]);
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

describe("remembered page size", () => {
  // The page size a user chose earlier in the session stands in for the
  // default when the URL has none (e.g. after the Resources tab or logotype).
  const parseWith = (search, fallbackPageSize) =>
    parseListParams(new URLSearchParams(search), { fallbackPageSize });
  const serializeWith = (state, fallbackPageSize) =>
    toListParams(state, { fallbackPageSize }).toString();

  it("uses the remembered size when the URL has no page_size", () => {
    expect(parseWith("", 50).pageSize).toBe(50);
  });

  it("lets the URL's page_size win over the remembered size", () => {
    expect(parseWith("page_size=25", 50).pageSize).toBe(25);
    expect(parseWith("page_size=10", 50).pageSize).toBe(10);
  });

  it("uses the remembered size when the URL's page_size is junk", () => {
    expect(parseWith("page_size=7", 50).pageSize).toBe(50);
  });

  it("keeps an explicit page_size=10 when the remembered size differs", () => {
    // Otherwise the next write would drop it and the list would jump to 50.
    expect(serializeWith({ ...DEFAULT_STATE, pageSize: 10 }, 50)).toBe(
      "page_size=10",
    );
  });

  it("still writes a non-default page size, so copied links show it", () => {
    expect(serializeWith({ ...DEFAULT_STATE, pageSize: 50 }, 50)).toBe(
      "page_size=50",
    );
  });

  it("round-trips any page size with a remembered size in place", () => {
    for (const pageSize of [10, 25, 50, 100]) {
      const state = { ...DEFAULT_STATE, pageSize };
      expect(
        parseListParams(toListParams(state, { fallbackPageSize: 50 }), {
          fallbackPageSize: 50,
        }),
      ).toEqual(state);
    }
  });
});

describe("page_size alongside other settings", () => {
  // With page size remembered per session, a link that leaves page_size out
  // would open at the recipient's remembered size -- and page=3 at 50 per
  // page is different rows from page=3 at 10. So any URL carrying other
  // state also carries page_size; only a bare "/" follows the viewer's size.
  const serializeWith = (state, fallbackPageSize = 10) =>
    decodeURIComponent(toListParams(state, { fallbackPageSize }).toString());

  it.each([
    [
      "a filter",
      { filters: { ...DEFAULT_STATE.filters, country: ["NOR"] } },
      "page_size=10&country=NOR",
    ],
    ["a page", { page: 3 }, "page=3&page_size=10"],
    ["a search", { q: "ghawar" }, "page_size=10&q=ghawar"],
    [
      "a sort",
      { sortBy: "name", sortOrder: "asc" },
      "page_size=10&sort_by=name&sort_order=asc",
    ],
  ])("writes page_size=10 with %s", (_, changes, expected) => {
    expect(serializeWith({ ...DEFAULT_STATE, ...changes })).toBe(expected);
  });

  it("still leaves a fully default view as a bare URL", () => {
    expect(serializeWith(DEFAULT_STATE)).toBe("");
  });

  it("writes a non-default size even when it is the remembered one", () => {
    expect(serializeWith({ ...DEFAULT_STATE, pageSize: 50 }, 50)).toBe(
      "page_size=50",
    );
  });

  it("leaves the default size out of an otherwise bare URL when it is also remembered", () => {
    expect(serializeWith({ ...DEFAULT_STATE, pageSize: 10 }, 10)).toBe("");
  });
});
