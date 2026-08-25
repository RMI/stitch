import { describe, expect, it } from "vitest";
import {
  FIELD_META,
  MERGE_COMPARISON_CORE_FIELDS,
  MERGE_COMPARISON_OTHER_FIELDS,
} from "./fieldMeta";

describe("merge comparison field constants", () => {
  it("defines the core comparison fields in display order", () => {
    expect(MERGE_COMPARISON_CORE_FIELDS).toEqual([
      "name",
      "country",
      "region",
      "basin",
      "state_province",
    ]);
  });

  it("keeps every core field a known FIELD_META key", () => {
    for (const key of MERGE_COMPARISON_CORE_FIELDS) {
      expect(FIELD_META[key]).toBeDefined();
    }
  });

  it("derives the other fields from FIELD_META, excluding core and organizations", () => {
    expect(MERGE_COMPARISON_OTHER_FIELDS).toEqual([
      "field_status",
      "production_start_year",
      "name_local",
      "latitude",
      "longitude",
      "location_type",
      "production_conventionality",
      "primary_hydrocarbon_group",
      "reservoir_formation",
      "discovery_year",
      "fid_year",
    ]);
  });

  it("leads the other fields with the most decision-relevant attributes", () => {
    expect(MERGE_COMPARISON_OTHER_FIELDS.slice(0, 2)).toEqual([
      "field_status",
      "production_start_year",
    ]);
  });

  it("keeps FIELD_META order for the remaining other fields", () => {
    const remaining = MERGE_COMPARISON_OTHER_FIELDS.slice(2);
    const fieldMetaOrder = Object.keys(FIELD_META).filter((key) =>
      remaining.includes(key),
    );

    expect(remaining).toEqual(fieldMetaOrder);
  });
});
