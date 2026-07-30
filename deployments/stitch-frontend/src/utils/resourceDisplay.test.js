import { describe, expect, it } from "vitest";
import {
  deriveProvenance,
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
      name: "wm",
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
