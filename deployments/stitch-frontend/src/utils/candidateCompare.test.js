import { describe, expect, it } from "vitest";
import {
  compareEntry,
  pickCompareName,
  valueEntryForResource,
} from "./candidateCompare";

function val(resourceId, value, priority) {
  return {
    source: "gem",
    source_id: priority + 1,
    value,
    priority,
    resource_id: resourceId,
  };
}

describe("compareEntry", () => {
  it("finds the entry for a field", () => {
    const compare = [{ field: "name", status: "match", values: [] }];
    expect(compareEntry(compare, "name")).toBe(compare[0]);
  });

  it("returns null for a missing field or missing compare", () => {
    expect(compareEntry([], "name")).toBeNull();
    expect(compareEntry(undefined, "name")).toBeNull();
  });
});

describe("valueEntryForResource", () => {
  const entry = {
    field: "name",
    status: "different",
    values: [val(101, "Burgan", 0), val(102, "Bergan", 1)],
  };

  it("returns the resource's winner-first entry", () => {
    expect(valueEntryForResource(entry, 102).value).toBe("Bergan");
  });

  it("returns null when the resource has no value", () => {
    expect(valueEntryForResource(entry, 999)).toBeNull();
    expect(valueEntryForResource(null, 101)).toBeNull();
  });
});

describe("pickCompareName", () => {
  it("returns the winning name value", () => {
    const compare = [
      {
        field: "name",
        status: "different",
        values: [val(101, "Burgan", 0), val(102, "Bergan", 1)],
      },
    ];
    expect(pickCompareName(compare)).toBe("Burgan");
  });

  it("returns null when there is no usable name", () => {
    expect(pickCompareName(undefined)).toBeNull();
    expect(pickCompareName([])).toBeNull();
    expect(
      pickCompareName([{ field: "name", status: "match", values: [] }]),
    ).toBeNull();
    expect(
      pickCompareName([
        { field: "name", status: "match", values: [val(101, "", 0)] },
      ]),
    ).toBeNull();
  });
});
