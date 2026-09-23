import { describe, it, expect, vi } from "vitest";
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

describe("FieldCard expandable behavior", () => {
  it("renders a plain box (no button) when not expandable", () => {
    render(<FieldCard label="Basin" value="Foo Basin" source="wm" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders a toggle button reflecting isOpen when expandable", () => {
    const { rerender } = render(
      <FieldCard label="Basin" value="Foo Basin" expandable isOpen={false} />,
    );
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    rerender(<FieldCard label="Basin" value="Foo Basin" expandable isOpen />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("calls onToggle when the value button is clicked", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <FieldCard
        label="Basin"
        value="Foo Basin"
        expandable
        onToggle={onToggle}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("keeps one disclosure marker and rotates it, rather than swapping glyphs", () => {
    // Two glyphs of different optical widths shifted the layout on toggle and
    // read as a flicker; one rotating marker shows what changed (STIT-748).
    const { rerender } = render(
      <FieldCard label="Basin" value="Foo Basin" expandable isOpen={false} />,
    );
    expect(screen.getByText("\u25B8")).not.toHaveClass("rotate-90");

    rerender(<FieldCard label="Basin" value="Foo Basin" expandable isOpen />);
    expect(screen.getByText("\u25B8")).toHaveClass("rotate-90");
  });

  it("renders the disclosure marker large enough to read", () => {
    render(
      <FieldCard label="Basin" value="Foo Basin" expandable isOpen={false} />,
    );
    // text-xs (12px) was the reported problem; text-lg is ~18px.
    expect(screen.getByText("\u25B8")).toHaveClass("text-lg");
  });

  it("renders children only when expandable and open", () => {
    const { rerender } = render(
      <FieldCard label="Basin" value="Foo Basin" expandable isOpen={false}>
        <div>panel body</div>
      </FieldCard>,
    );
    expect(screen.queryByText("panel body")).not.toBeInTheDocument();

    rerender(
      <FieldCard label="Basin" value="Foo Basin" expandable isOpen>
        <div>panel body</div>
      </FieldCard>,
    );
    expect(screen.getByText("panel body")).toBeInTheDocument();
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
