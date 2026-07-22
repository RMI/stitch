import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResourceFieldCard from "./ResourceFieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
import { SOURCE_LABELS } from "../constants/sourceMeta";

vi.mock("../hooks/useResources", () => ({
  useFieldSourceValues: vi.fn(),
}));

function renderCard(props = {}) {
  return render(
    <ResourceFieldCard
      endpoint="oil-gas-fields"
      resourceId={42}
      fieldKey="basin"
      label="Basin"
      value="Foo Basin"
      source="wm"
      {...props}
    />,
  );
}

describe("ResourceFieldCard", () => {
  beforeEach(() => {
    useFieldSourceValues.mockReset();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
  });

  it("is not expandable when the value is empty", () => {
    renderCard({ value: null });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not enable the query until the panel is opened", () => {
    renderCard();
    // Closed on first render → query disabled.
    expect(useFieldSourceValues).toHaveBeenLastCalledWith(
      "oil-gas-fields",
      42,
      "basin",
      false,
    );
  });

  it("enables the query and shows the panel when opened", async () => {
    const user = userEvent.setup();
    useFieldSourceValues.mockReturnValue({
      data: [
        { source: "wm", source_id: 20, value: "Foo Basin", priority: 1 },
        { source: "gem", source_id: 10, value: "Bar Basin", priority: 2 },
      ],
      isLoading: false,
      isError: false,
    });
    renderCard();

    await user.click(screen.getByRole("button"));

    expect(useFieldSourceValues).toHaveBeenLastCalledWith(
      "oil-gas-fields",
      42,
      "basin",
      true,
    );
    expect(screen.getByText("All sources")).toBeInTheDocument();
    expect(screen.getByText('"Foo Basin"')).toBeInTheDocument();
    expect(screen.getByText('"Bar Basin"')).toBeInTheDocument();
    expect(screen.getByText(`${SOURCE_LABELS.wm} · #20`)).toBeInTheDocument();
  });

  it("highlights the first (winning) row and diminishes the rest", async () => {
    const user = userEvent.setup();
    useFieldSourceValues.mockReturnValue({
      data: [
        { source: "wm", source_id: 20, value: "Foo Basin", priority: 1 },
        { source: "gem", source_id: 10, value: "Bar Basin", priority: 2 },
      ],
      isLoading: false,
      isError: false,
    });
    renderCard();
    await user.click(screen.getByRole("button"));

    expect(screen.getByText('"Foo Basin"').closest(".border-l-4")).toHaveClass(
      "bg-surface",
    );
    expect(screen.getByText('"Bar Basin"').closest(".border-l-4")).toHaveClass(
      "bg-panel",
    );
  });

  it("shows a loading state while fetching", async () => {
    const user = userEvent.setup();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    renderCard();
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Loading sources…")).toBeInTheDocument();
  });

  it("shows an error state when the fetch fails", async () => {
    const user = userEvent.setup();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });
    renderCard();
    await user.click(screen.getByRole("button"));
    expect(
      screen.getByText("Failed to load source values."),
    ).toBeInTheDocument();
  });
});
