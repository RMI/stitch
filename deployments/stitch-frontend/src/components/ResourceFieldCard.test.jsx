import { useState } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResourceFieldCard from "./ResourceFieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
import {
  useHasPermission,
  useHasAllPermissions,
} from "../hooks/usePermissions";
import {
  updateFieldSourcePriority,
  createSourceForResource,
} from "../queries/api";
import { SOURCE_LABELS } from "../constants/sourceMeta";
import { renderWithQueryClient } from "../test/utils";

// Mock only the read hook; the save path exercises the real
// useCreateSourceForResource mutation against a spied API module.
vi.mock("../hooks/useResources", async (importOriginal) => ({
  ...(await importOriginal()),
  useFieldSourceValues: vi.fn(),
}));
vi.mock("../hooks/usePermissions", () => ({
  useHasPermission: vi.fn(),
  useHasAllPermissions: vi.fn(),
}));
vi.mock("../queries/api", () => ({
  updateFieldSourcePriority: vi.fn(),
  createSourceForResource: vi.fn(),
}));

const TWO_SOURCES = [
  {
    source: "wm",
    source_id: 20,
    value: "Foo Basin",
    priority: 0,
    is_override: false,
  },
  {
    source: "gem",
    source_id: 10,
    value: "Bar Basin",
    priority: 1,
    is_override: false,
  },
];

// Grant both writes required to create + attach a source.
function grantWritePermissions() {
  vi.mocked(useHasPermission).mockImplementation((permission) =>
    ["source:write", "resource:write"].includes(permission),
  );
}

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

// Renders the card plus a button that forces a parent re-render -- standing in for
// a background refetch -- without unmounting the open panel, so its edit state
// survives while `useFieldSourceValues` reports new data.
function RefetchHarness() {
  const [, setTick] = useState(0);
  return (
    <>
      <button onClick={() => setTick((tick) => tick + 1)}>refetch</button>
      <ResourceFieldCard
        endpoint="oil-gas-fields"
        resourceId={42}
        fieldKey="basin"
        label="Basin"
        value="Foo Basin"
        source="wm"
      />
    </>
  );
}

describe("ResourceFieldCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
    // Default: no permissions, so the edit affordance stays hidden.
    useHasPermission.mockReturnValue(false);
    useHasAllPermissions.mockReturnValue(false);
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

  it("does not show an Edit button without any write permission", async () => {
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

  it("offers add but not reorder controls when only one source has a value", async () => {
    const user = userEvent.setup();
    // Both writes → the field can still be edited to add a value...
    grantWritePermissions();
    useFieldSourceValues.mockReturnValue({
      data: [TWO_SOURCES[0]],
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: "Edit" }));

    // ...the add affordance is present...
    expect(
      screen.getByRole("button", { name: /add value/i }),
    ).toBeInTheDocument();
    // ...but a lone source cannot be reordered: no move arrows, no reorder Save.
    expect(
      screen.queryByRole("button", { name: `Move ${SOURCE_LABELS.wm} up` }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
  });

  it("does not offer reorder controls without read access to all sources", async () => {
    const user = userEvent.setup();
    // Curator writes but is missing at least one source:read, so reordering (which
    // rewrites every source's ranking) is withheld even with two sources.
    grantWritePermissions();
    useHasAllPermissions.mockReturnValue(false);
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderCard();
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: "Edit" }));

    // Add is still available (it needs only source:write + resource:write)...
    expect(
      screen.getByRole("button", { name: /add value/i }),
    ).toBeInTheDocument();
    // ...but the reorder affordances are withheld.
    expect(
      screen.queryByRole("button", { name: `Move ${SOURCE_LABELS.gem} up` }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
  });

  it("reorders sources and saves the new priority order", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(true);
    useHasAllPermissions.mockReturnValue(true);
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

  it("warns and blocks the save when the source set changes mid-edit", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(true);
    useHasAllPermissions.mockReturnValue(true);
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });

    renderWithQueryClient(<RefetchHarness />);

    await user.click(screen.getByRole("button", { name: /Foo Basin/i }));
    await user.click(screen.getByRole("button", { name: "Edit" }));

    // A source is added under the open panel, so the working order no longer
    // matches the source set a save would target.
    useFieldSourceValues.mockReturnValue({
      data: [
        ...TWO_SOURCES,
        {
          source: "ccr",
          source_id: 30,
          value: "Baz Basin",
          priority: 2,
          is_override: false,
        },
      ],
      isLoading: false,
      isError: false,
    });
    await user.click(screen.getByRole("button", { name: "refetch" }));

    expect(screen.getByText(/source list changed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("blocks the save when the same sources are reordered server-side mid-edit", async () => {
    const user = userEvent.setup();
    useHasPermission.mockReturnValue(true);
    useHasAllPermissions.mockReturnValue(true);
    useFieldSourceValues.mockReturnValue({
      data: TWO_SOURCES,
      isLoading: false,
      isError: false,
    });
    renderWithQueryClient(<RefetchHarness />);

    await user.click(screen.getByRole("button", { name: /Foo Basin/i }));
    await user.click(screen.getByRole("button", { name: "Edit" }));

    // Someone else reorders the *same* sources while the panel is open and the
    // curator has not touched anything. Save must not spuriously enable (which
    // would overwrite the newer order with a stale snapshot); the notice shows.
    useFieldSourceValues.mockReturnValue({
      data: [TWO_SOURCES[1], TWO_SOURCES[0]],
      isLoading: false,
      isError: false,
    });
    await user.click(screen.getByRole("button", { name: "refetch" }));

    expect(screen.getByText(/source list changed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
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

  it("lets an editor expand a field that has no values to add the first one", async () => {
    const user = userEvent.setup();
    grantWritePermissions();
    useFieldSourceValues.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    renderCard({ value: null });

    await user.click(screen.getByRole("button"));

    expect(useFieldSourceValues).toHaveBeenLastCalledWith(
      "oil-gas-fields",
      42,
      "basin",
      true,
    );
    expect(
      screen.getByText("No source values for this field."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });

  describe("overwrite action", () => {
    beforeEach(() => {
      useFieldSourceValues.mockReturnValue({
        data: [{ source: "wm", source_id: 20, value: "Foo Basin" }],
        isLoading: false,
        isError: false,
      });
    });

    it("hides the Edit action without both write permissions", async () => {
      const user = userEvent.setup();
      // Only source:write, missing resource:write.
      vi.mocked(useHasPermission).mockImplementation(
        (permission) => permission === "source:write",
      );
      renderCard();
      await user.click(screen.getByRole("button"));

      expect(
        screen.queryByRole("button", { name: /^edit$/i }),
      ).not.toBeInTheDocument();
    });

    it("keeps the value form hidden until '+' is clicked, and Cancel resets", async () => {
      const user = userEvent.setup();
      grantWritePermissions();
      renderCard();
      await user.click(screen.getByRole("button")); // open panel

      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      // Only the "+" affordance shows; the fields stay hidden until it's clicked.
      expect(
        screen.getByRole("button", { name: /add value/i }),
      ).toBeInTheDocument();
      expect(screen.queryByLabelText("New value")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /add value/i }));
      expect(screen.getByLabelText("New value")).toBeInTheDocument();
      expect(screen.getByLabelText("Note")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /^save$/i }),
      ).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /^cancel$/i }));
      expect(screen.queryByLabelText("New value")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /add value/i }),
      ).not.toBeInTheDocument();
    });

    it("creates an rmi source with only this field populated, plus the note, and refreshes", async () => {
      const user = userEvent.setup();
      grantWritePermissions();
      createSourceForResource.mockResolvedValue({ id: 99, source: "rmi" });

      const { queryClient } = renderCard();
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      await user.click(screen.getByRole("button")); // open panel
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      await user.type(screen.getByLabelText("Note"), "checked the map");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(createSourceForResource).toHaveBeenCalledWith(
        expect.objectContaining({
          apiBaseUrl: "http://localhost:8000/api/v1",
        }),
        42,
        expect.objectContaining({
          source: "rmi",
          name: null,
          country: null,
          basin: "Deep Basin",
          source_record: expect.objectContaining({
            record_id: null,
            run_id: null,
            producer: "stitch-frontend",
            observed_at: expect.any(String),
            payload: {
              action: "field_overwrite",
              field: "basin",
              value: "Deep Basin",
              note: "checked the map",
            },
          }),
        }),
        expect.any(Function),
        "oil-gas-fields",
      );

      // A save can change the coalesced winning value anywhere it appears
      // (list rows, detail, filter options), so the whole endpoint refreshes.
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["oil-gas-fields"],
      });

      // Form closes on success.
      expect(
        await screen.findByRole("button", { name: /^edit$/i }),
      ).toBeInTheDocument();
    });

    it("sends a null note when the note field is left blank", async () => {
      const user = userEvent.setup();
      grantWritePermissions();
      createSourceForResource.mockResolvedValue({ id: 100, source: "rmi" });

      renderCard();
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(createSourceForResource).toHaveBeenCalledWith(
        expect.anything(),
        42,
        expect.objectContaining({
          source_record: expect.objectContaining({
            payload: expect.objectContaining({ note: null }),
          }),
        }),
        expect.any(Function),
        "oil-gas-fields",
      );
    });

    it("surfaces the API error and preserves the draft", async () => {
      const user = userEvent.setup();
      grantWritePermissions();
      createSourceForResource.mockRejectedValue(new Error("overwrite failed"));

      renderCard();
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(await screen.findByText("overwrite failed")).toBeInTheDocument();
      // Draft is preserved so the user can retry.
      expect(screen.getByLabelText("New value")).toHaveValue("Deep Basin");
    });

    it("keeps the Save button disabled until a value is entered", async () => {
      const user = userEvent.setup();
      grantWritePermissions();
      renderCard();
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));

      expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      expect(
        screen.getByRole("button", { name: /^save$/i }),
      ).not.toBeDisabled();
    });
  });
});
