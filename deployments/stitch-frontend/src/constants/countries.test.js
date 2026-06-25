import { describe, it, expect } from "vitest";
import { getCountryName, ALPHA3_TO_ALPHA2 } from "./countries";

describe("getCountryName", () => {
  it("maps known alpha-3 codes to conventional names", () => {
    expect(getCountryName("NOR")).toBe("Norway");
    expect(getCountryName("SAU")).toBe("Saudi Arabia");
    expect(getCountryName("DZA")).toBe("Algeria");
    expect(getCountryName("IRQ")).toBe("Iraq");
    expect(getCountryName("KAZ")).toBe("Kazakhstan");
    expect(getCountryName("NGA")).toBe("Nigeria");
  });

  it("falls back to the raw value for unknown codes", () => {
    expect(getCountryName("XYZ")).toBe("XYZ");
    expect(getCountryName("ZZZ")).toBe("ZZZ");
  });

  it("returns falsy/empty inputs unchanged", () => {
    expect(getCountryName(null)).toBeNull();
    expect(getCountryName(undefined)).toBeUndefined();
    expect(getCountryName("")).toBe("");
  });

  it("does not match lowercase codes (data is uppercase alpha-3)", () => {
    // Lookup is case-sensitive; lowercase isn't a known code, so it passes through.
    expect(getCountryName("nor")).toBe("nor");
  });
});

describe("ALPHA3_TO_ALPHA2", () => {
  it("maps each alpha-3 code to a two-letter alpha-2 code", () => {
    for (const [alpha3, alpha2] of Object.entries(ALPHA3_TO_ALPHA2)) {
      expect(alpha3).toMatch(/^[A-Z]{3}$/);
      expect(alpha2).toMatch(/^[A-Z]{2}$/);
    }
  });

  it("contains the codes used by the seed/mock data", () => {
    for (const code of ["DZA", "IRQ", "KAZ", "NGA", "NOR", "SAU"]) {
      expect(ALPHA3_TO_ALPHA2).toHaveProperty(code);
    }
  });

  it("has no duplicate alpha-2 codes", () => {
    const alpha2s = Object.values(ALPHA3_TO_ALPHA2);
    expect(new Set(alpha2s).size).toBe(alpha2s.length);
  });
});
