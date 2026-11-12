import { describe, expect, it } from "vitest";
import { candidateDisplayName } from "./mergeCandidateName";

describe("candidateDisplayName", () => {
  it("uses the API's display name", () => {
    expect(candidateDisplayName({ id: 7, display_name: "Burgan" })).toBe(
      "Burgan",
    );
  });

  it("falls back to the candidate id when there is no name", () => {
    expect(candidateDisplayName({ id: 7, display_name: null })).toBe(
      "Candidate #7",
    );
    expect(candidateDisplayName({ id: 7 })).toBe("Candidate #7");
  });
});
