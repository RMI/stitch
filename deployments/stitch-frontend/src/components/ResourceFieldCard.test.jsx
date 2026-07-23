import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResourceFieldCard from "./ResourceFieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import { updateFieldSourcePriority } from "../queries/api";
import { SOURCE_LABELS } from "../constants/sourceMeta";

vi.mock("../hooks/useResources", () => ({
  useFieldSourceValues: vi.fn(),
}));
vi.mock("../hooks/usePermissions", () => ({
  useHasPermission: vi.fn(),
}));
vi.mock("../config/useConfig", () => ({
  useConfig: () => ({ apiBaseUrl: "http://api.test" }),
}));
vi.mock("@auth0/auth0-react", () => ({
  useAuth0: () => ({ getAccessTokenSilently: vi.fn() }),
}));
const invalidateQueries = vi.fn(() => Promise.resolve());
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries }),
}));
vi.mock("../queries/api", () => ({
  updateFieldSourcePriority: vi.fn(() => Promise.resolve([])),
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

const TWO_SOURCES = [
  { source: "wm", source_id: 20, value: "Foo Basin", priority: 1 },
  { source: "gem", source_id: 10, value: "Bar Basin", priority: 2 },
];

describe("ResourceFieldCard", () => {
  beforeEach(() => {
    useFieldSourceValues.mockReset();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
    // Default: no write permission, so the Edit control is hidden.
    useHasPermission.mockReset();
    useHasPermission.mockReturnValue(false);
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
      data: TWO_SOURCES,
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

describe("ResourceFieldCard edit mode", () => {
  beforeEach(() => {
    useFieldSourceValues.mockReset();
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    useHasPermission.mockReset();
    useHasPermission.mockReturnValue(true);
    invalidateQueries.mockClear();
    updateFieldSourcePriority.mockClear();
    updateFieldSourcePriority.mockResolvedValue([]);
  });

  async function openPanel(user) {
    await user.click(screen.getByRole("button", { name: /Foo Basin/ }));
  }

  it("hides the Edit button without write permission", async () => {
    useHasPermission.mockReturnValue(false);
    const user = userEvent.setup();
    renderCard();
    await openPanel(user);
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("hides the Edit button when there is only one source", async () => {
    useFieldSourceValues.mockReturnValue({
      data: [TWO_SOURCES[0]],
      isLoading: false,
      isError: false,
    });
    const user = userEvent.setup();
    renderCard();
    await openPanel(user);
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("enters edit mode and disables Save until the order changes", async () => {
    const user = userEvent.setup();
    renderCard();
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("enables Save after reordering and posts the new order", async () => {
    const user = userEvent.setup();
    renderCard();
    await openPanel(user);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    // Move the second source (gem, #10) up above the winner (wm, #20).
    await user.click(
      screen.getByRole("button", { name: "Move GEM Database up" }),
    );

    const saveButton = screen.getByRole("button", { name: "Save" });
    expect(saveButton).toBeEnabled();

    await user.click(saveButton);

    expect(updateFieldSourcePriority).toHaveBeenCalledWith(
      expect.anything(),
      42,
      "basin",
      [10, 20],
      expect.anything(),
      "oil-gas-fields",
    );
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalled());
  });

  it("leaves edit mode on Cancel without saving", async () => {
    const user = userEvent.setup();
    renderCard();
    await openPanel(user);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(updateFieldSourcePriority).not.toHaveBeenCalled();
  });
});
