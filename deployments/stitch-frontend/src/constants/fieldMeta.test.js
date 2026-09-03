import { describe, expect, it } from "vitest";
import {
  FIELD_META,
  MERGE_COMPARISON_CORE_FIELDS,
  MERGE_COMPARISON_OTHER_FIELDS,
} from "./fieldMeta";

// Mirrors MERGE_COMPARISON_LEAD_OTHER_FIELDS, which is private to the module.
const LEAD_FIELDS = ["field_status", "production_start_year"];

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

  it("keeps every other field a known FIELD_META key and excludes core/org fields", () => {
    for (const key of MERGE_COMPARISON_OTHER_FIELDS) {
      expect(FIELD_META[key]).toBeDefined();
      expect(FIELD_META[key].section).not.toBe("organizations");
      expect(MERGE_COMPARISON_CORE_FIELDS).not.toContain(key);
    }
  });

  it("leads the other fields with the most decision-relevant attributes", () => {
    expect(MERGE_COMPARISON_OTHER_FIELDS.slice(0, LEAD_FIELDS.length)).toEqual(
      LEAD_FIELDS,
    );
  });

  it("keeps FIELD_META order for the remaining other fields", () => {
    const remaining = MERGE_COMPARISON_OTHER_FIELDS.slice(LEAD_FIELDS.length);
    const fieldMetaOrder = Object.keys(FIELD_META).filter((key) =>
      remaining.includes(key),
    );

    expect(remaining).toEqual(fieldMetaOrder);
  });
});
