import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResourceFieldCard from "./ResourceFieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import { updateFieldSourcePriority } from "../queries/api";
import { SOURCE_LABELS } from "../constants/sourceMeta";
import { renderWithQueryClient } from "../test/utils";

vi.mock("../hooks/useResources", () => ({
  useFieldSourceValues: vi.fn(),
}));
vi.mock("../hooks/usePermissions", () => ({
  useHasPermission: vi.fn(),
}));
vi.mock("../queries/api", () => ({
  updateFieldSourcePriority: vi.fn(),
}));

const TWO_SOURCES = [
  { source: "wm", id: 20, value: "Foo Basin", priority: 0, is_override: false },
  {
    source: "gem",
    id: 10,
    value: "Bar Basin",
    priority: 1,
    is_override: false,
  },
];

function renderCard(props = {}) {
  return renderWithQueryClient(
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

async function openPanel(user) {
  await user.click(screen.getByRole("button", { name: /Foo Basin/i }));
}

describe("ResourceFieldCard", () => {
  beforeEach(() => {
    useFieldSourceValues.mockReset();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
    useHasPermission.mockReset();
    useHasPermission.mockReturnValue(false);
    updateFieldSourcePriority.mockReset();
    updateFieldSourcePriority.mockResolvedValue([]);
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
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderCard();

    await openPanel(user);

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
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);

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
    await openPanel(user);
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
    await openPanel(user);
    expect(
      screen.getByText("Failed to load source values."),
    ).toBeInTheDocument();
  });

  it("does not show an Edit button without resource:write", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(false);
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("does not show an Edit button when only one source has a value", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(true);
    useFieldSourceValues.mockReturnValue({
      data: [TWO_SOURCES[0]],
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("reorders sources and saves the new priority order", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(true);
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: "Edit" }));

    // Save is disabled until the order actually changes.
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    // Promote the second source (gem) above the winner.
    await user.click(
      screen.getByRole("button", { name: `Move ${SOURCE_LABELS.gem} up` }),
    );

    const saveButton = screen.getByRole("button", { name: "Save" });
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    expect(updateFieldSourcePriority).toHaveBeenCalledTimes(1);
    const call = updateFieldSourcePriority.mock.calls[0];
    // (config, id, field, orderedSourcePks, fetcher, endpoint)
    expect(call[1]).toBe(42);
    expect(call[2]).toBe("basin");
    expect(call[3]).toEqual([10, 20]);
    expect(call[5]).toBe("oil-gas-fields");
  });

  it("badges curated (overridden) rows", async () => {
    const user = userEvent.setup();
    useFieldSourceValues.mockReturnValue({
      data: [{ ...TWO_SOURCES[0], is_override: true }, TWO_SOURCES[1]],
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);

    const winnerRow = screen.getByText('"Foo Basin"').closest(".border-l-4");
    expect(within(winnerRow).getByText("curated")).toBeInTheDocument();
  });
});
