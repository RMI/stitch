import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import SourceMixBar from "./SourceMixBar";
import { SOURCE_LABELS, UNKNOWN_SOURCE_LABEL } from "../constants/sourceMeta";

const singleSource = { foo: "gem", bar: "gem", baz: null };
const mixedSources = { foo: "gem", bar: "wm", baz: null };
const noSources = { foo: null, bar: null, baz: null };
const unknownSources = { foo: "gem", bar: "external", baz: null };

describe("SourceMixBar", () => {
  it("renders a placeholder bar when all source counts are zero", () => {
    const { container } = render(<SourceMixBar provenance={noSources} />);
    const bar = container.querySelector("[title='No source data']");
    expect(bar).toBeInTheDocument();
    expect(
      screen.getByRole("group", {
        name: /data source mix: no source data available/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No source data")).toBeInTheDocument();
  });

  it("renders a placeholder bar when provenance is undefined", () => {
    const { container } = render(<SourceMixBar provenance={undefined} />);
    const bar = container.querySelector("[title='No source data']");
    expect(bar).toBeInTheDocument();
  });

  it("renders bar segments for active sources", () => {
    const { container } = render(<SourceMixBar provenance={mixedSources} />);
    const segments = container.querySelectorAll("[title]");
    // Each active source gets a titled segment
    expect(segments.length).toBeGreaterThanOrEqual(2);
  });

  it("renders a text source summary by default", () => {
    render(<SourceMixBar provenance={singleSource} />);
    expect(
      screen.getByText(`${SOURCE_LABELS.gem}: 2 fields (100%)`),
    ).toBeInTheDocument();
  });

  it("renders source labels when showLabels is true", () => {
    render(<SourceMixBar provenance={singleSource} showLabels />);
    expect(
      screen.getByText(`${SOURCE_LABELS.gem}: 2 fields (100%)`),
    ).toBeInTheDocument();
  });

  it("only renders labels for sources with records", () => {
    render(<SourceMixBar provenance={singleSource} showLabels />);
    // wm has 0 records — its label should not appear
    expect(screen.queryByText(SOURCE_LABELS.wm)).not.toBeInTheDocument();
  });

  it("renders labels for all active sources in a mixed dataset", () => {
    render(<SourceMixBar provenance={mixedSources} showLabels />);
    expect(
      screen.getByText(`${SOURCE_LABELS.gem}: 1 field (50%)`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${SOURCE_LABELS.wm}: 1 field (50%)`),
    ).toBeInTheDocument();
  });

  it("includes a readable summary for assistive technologies", () => {
    render(<SourceMixBar provenance={mixedSources} />);
    expect(
      screen.getByRole("group", {
        name: /data source mix: woodmac database: 1 field \(50%\); gem database: 1 field \(50%\)/i,
      }),
    ).toBeInTheDocument();
  });

  it("does not drop unknown provenance values", () => {
    render(<SourceMixBar provenance={unknownSources} showLabels />);
    expect(
      screen.getByText(`${SOURCE_LABELS.gem}: 1 field (50%)`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${UNKNOWN_SOURCE_LABEL}: 1 field (50%)`),
    ).toBeInTheDocument();
  });
});
