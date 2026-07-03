import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FieldCard, FieldGrid } from "./FieldCard";
import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

describe("FieldCard", () => {
  it("renders the label", () => {
    render(<FieldCard label="Country" value="Kuwait" />);
    expect(screen.getByText("Country")).toBeInTheDocument();
  });

  it("renders a string value", () => {
    render(<FieldCard label="Country" value="Kuwait" />);
    expect(screen.getByText("Kuwait")).toBeInTheDocument();
  });

  it("renders a numeric value as a string", () => {
    render(<FieldCard label="Discovery Year" value={1938} />);
    expect(screen.getByText("1938")).toBeInTheDocument();
  });

  it("renders an em dash for null value", () => {
    render(<FieldCard label="Basin" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an em dash for undefined value", () => {
    render(<FieldCard label="Basin" value={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an em dash for empty string value", () => {
    render(<FieldCard label="Basin" value="" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("applies the border color for a known source", () => {
    const { container } = render(
      <FieldCard label="Country" value="Kuwait" source="gem" />,
    );
    // The value box is the only element with an inline border-left style
    const valueBox = container.querySelector("[style]");
    expect(valueBox).toHaveStyle({ borderLeftColor: SOURCE_COLORS.gem });
  });

  it("renders a visible source label for a known source", () => {
    render(<FieldCard label="Country" value="Kuwait" source="gem" />);
    expect(
      screen.getByText(`Source: ${SOURCE_LABELS.gem}`),
    ).toBeInTheDocument();
  });

  it("falls back to the default border color for an unknown source", () => {
    const { container } = render(
      <FieldCard label="Country" value="Kuwait" source="unknown" />,
    );
    const valueBox = container.querySelector("[style]");
    expect(valueBox).toHaveStyle({ borderLeftColor: DEFAULT_FIELD_COLOR });
  });

  it("renders an unavailable source label for an unknown source", () => {
    render(<FieldCard label="Country" value="Kuwait" source="unknown" />);
    expect(
      screen.getByText(`Source: ${UNKNOWN_SOURCE_LABEL}`),
    ).toBeInTheDocument();
  });

  it("uses the default border color when source is omitted", () => {
    const { container } = render(<FieldCard label="Country" value="Kuwait" />);
    const valueBox = container.querySelector("[style]");
    expect(valueBox).toHaveStyle({ borderLeftColor: DEFAULT_FIELD_COLOR });
  });

  it("does not render source copy when source is omitted", () => {
    render(<FieldCard label="Country" value="Kuwait" />);
    expect(screen.queryByText(/^Source:/)).not.toBeInTheDocument();
  });
});

describe("FieldCard sources panel", () => {
  const sources = [
    { id: 20, source: "wm", value: "Foo Basin", isWinner: true },
    { id: 10, source: "gem", value: "Bar Basin", isWinner: false },
  ];

  it("is not interactive when no sources are provided", () => {
    render(<FieldCard label="Basin" value="Foo Basin" source="wm" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("All sources")).not.toBeInTheDocument();
  });

  it("is not interactive when sources is empty", () => {
    render(<FieldCard label="Basin" value="Foo Basin" source="wm" sources={[]} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("reveals the All sources panel on click and hides it again", async () => {
    const user = userEvent.setup();
    render(
      <FieldCard label="Basin" value="Foo Basin" source="wm" sources={sources} />,
    );

    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("All sources")).not.toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("All sources")).toBeInTheDocument();
    expect(screen.getByText('"Foo Basin"')).toBeInTheDocument();
    expect(screen.getByText('"Bar Basin"')).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.queryByText("All sources")).not.toBeInTheDocument();
  });

  it("highlights the coalesced winner's row", async () => {
    const user = userEvent.setup();
    render(
      <FieldCard label="Basin" value="Foo Basin" source="wm" sources={sources} />,
    );
    await user.click(screen.getByRole("button"));

    const winnerRow = screen.getByText('"Foo Basin"').closest(".border-l-4");
    const loserRow = screen.getByText('"Bar Basin"').closest(".border-l-4");
    expect(winnerRow).toHaveClass("bg-surface");
    expect(loserRow).toHaveClass("bg-panel");
  });

  it("orders rows winner-first (priority order)", async () => {
    const user = userEvent.setup();
    render(
      <FieldCard label="Basin" value="Foo Basin" source="wm" sources={sources} />,
    );
    await user.click(screen.getByRole("button"));
    const values = screen
      .getAllByText(/^".*"$/)
      .map((el) => el.textContent);
    expect(values).toEqual(['"Foo Basin"', '"Bar Basin"']);
  });

  it("shows the source label and row id beneath each value", async () => {
    const user = userEvent.setup();
    render(
      <FieldCard label="Basin" value="Foo Basin" source="wm" sources={sources} />,
    );
    await user.click(screen.getByRole("button"));
    expect(
      screen.getByText(`${SOURCE_LABELS.wm} · #20`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${SOURCE_LABELS.gem} · #10`),
    ).toBeInTheDocument();
  });
});

describe("FieldGrid", () => {
  it("renders its children", () => {
    render(
      <FieldGrid>
        <FieldCard label="Name" value="Burgan" />
        <FieldCard label="Country" value="Kuwait" />
      </FieldGrid>,
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Country")).toBeInTheDocument();
  });
});
