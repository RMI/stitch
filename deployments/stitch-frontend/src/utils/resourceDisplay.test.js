import { describe, expect, it } from "vitest";
import {
  deriveProvenance,
  getFieldSources,
  getResourceField,
  isPrimitive,
  normalizeResourceListItem,
} from "./resourceDisplay";

describe("resourceDisplay utilities", () => {
  it("derives field provenance using source order for duplicate matches", () => {
    const resource = {
      data: {
        id: 1,
        name: "Shared field",
        basin: "Arabian",
        owners: [{ name: "Operator" }],
      },
      source_data: {
        gem: [{ name: "Shared field" }],
        wm: [{ name: "Shared field", basin: "Arabian" }],
        rmi: [],
        llm: [],
      },
    };

    expect(deriveProvenance(resource)).toEqual({
      name: "gem",
      basin: "wm",
    });
  });

  it("normalizes flat resource items into data without metadata fields", () => {
    const resource = {
      id: "field-1",
      source_data: {
        gem: [{ name: "Burgan", basin: "Arabian" }],
        wm: [],
        rmi: [],
        llm: [],
      },
      repointed_to: null,
      constituents: [],
      provenance: { name: "gem" },
      name: "Burgan",
      basin: "Arabian",
    };

    const normalized = normalizeResourceListItem(resource);

    expect(normalized.id).toBe("field-1");
    expect(normalized.data).toEqual({
      name: "Burgan",
      basin: "Arabian",
    });
    expect(normalized.data).not.toHaveProperty("source_data");
    expect(normalized.provenance).toEqual({ name: "gem" });
  });

  it("returns already-normalized resources unchanged", () => {
    const resource = {
      id: "field-1",
      data: { name: "Burgan" },
      provenance: { name: "gem" },
    };

    expect(normalizeResourceListItem(resource)).toBe(resource);
  });

  it("prefers normalized data values when reading fields", () => {
    expect(
      getResourceField(
        { name: "Top-level", data: { name: "Normalized" } },
        "name",
      ),
    ).toBe("Normalized");
  });

  it("treats scalar and empty values as primitive", () => {
    expect(isPrimitive(null)).toBe(true);
    expect(isPrimitive("value")).toBe(true);
    expect(isPrimitive(1)).toBe(true);
    expect(isPrimitive(false)).toBe(true);
    expect(isPrimitive({ value: 1 })).toBe(false);
    expect(isPrimitive([1])).toBe(false);
  });
});

describe("getFieldSources", () => {
  const detailView = {
    data: { basin: "Foo Basin" },
    provenance: { basin: "wm" },
    // wm outranks gem outranks llm for this resource.
    source_priority: { wm: 1, gem: 2, llm: 3 },
    source_data: [
      { id: 10, source: "gem", basin: "Bar Basin" },
      { id: 20, source: "wm", basin: "Foo Basin" },
      { id: 30, source: "llm", basin: "" },
      { id: 40, source: "gem", basin: null },
    ],
  };

  it("marks the coalesced winner and orders losers by priority", () => {
    expect(getFieldSources(detailView, "basin")).toEqual([
      { id: 20, source: "wm", value: "Foo Basin", isWinner: true },
      { id: 10, source: "gem", value: "Bar Basin", isWinner: false },
    ]);
  });

  it("excludes records with empty, null, or undefined values", () => {
    const rows = getFieldSources(detailView, "basin");
    expect(rows.map((r) => r.id)).toEqual([20, 10]);
    expect(rows.map((r) => r.id)).not.toContain(30);
    expect(rows.map((r) => r.id)).not.toContain(40);
  });

  it("keeps duplicate same-source records, tie-broken by id", () => {
    const view = {
      data: { basin: "Foo Basin" },
      provenance: { basin: "rmi" },
      source_priority: { rmi: 1 },
      source_data: [
        { id: 30, source: "rmi", basin: "Other" },
        { id: 10, source: "rmi", basin: "Foo Basin" },
        { id: 20, source: "rmi", basin: "Other" },
      ],
    };
    expect(getFieldSources(view, "basin")).toEqual([
      { id: 10, source: "rmi", value: "Foo Basin", isWinner: true },
      { id: 20, source: "rmi", value: "Other", isWinner: false },
      { id: 30, source: "rmi", value: "Other", isWinner: false },
    ]);
  });

  it("returns an empty array when nothing has a value", () => {
    expect(
      getFieldSources(
        {
          data: {},
          provenance: {},
          source_priority: {},
          source_data: [{ id: 1, source: "gem", basin: null }],
        },
        "basin",
      ),
    ).toEqual([]);
  });

  it("orders gracefully when source_priority is missing", () => {
    const view = {
      data: { basin: "Foo Basin" },
      provenance: { basin: "wm" },
      source_data: [
        { id: 10, source: "gem", basin: "Bar Basin" },
        { id: 20, source: "wm", basin: "Foo Basin" },
      ],
    };
    const rows = getFieldSources(view, "basin");
    expect(rows[0]).toEqual({
      id: 20,
      source: "wm",
      value: "Foo Basin",
      isWinner: true,
    });
    expect(rows).toHaveLength(2);
  });
});
