import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithQueryClient } from "../test/utils";
import ResourceFieldCard from "./ResourceFieldCard";
import { useFieldSourceValues } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import * as apiModule from "../queries/api";
import { SOURCE_LABELS } from "../constants/sourceMeta";

// Mock only the read hook; the save path exercises the real
// useCreateSourceForResource mutation against a spied API module.
vi.mock("../hooks/useResources", async (importOriginal) => ({
  ...(await importOriginal()),
  useFieldSourceValues: vi.fn(),
}));
vi.mock("../hooks/usePermissions", () => ({
  useHasPermission: vi.fn(),
}));

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

describe("ResourceFieldCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useFieldSourceValues.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
    // Default: no permissions, so the edit affordance stays hidden.
    vi.mocked(useHasPermission).mockReturnValue(false);
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
      const createSpy = vi
        .spyOn(apiModule, "createSourceForResource")
        .mockResolvedValue({ id: 99, source: "rmi" });

      const { queryClient } = renderCard();
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      await user.click(screen.getByRole("button")); // open panel
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      await user.type(screen.getByLabelText("Note"), "checked the map");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(createSpy).toHaveBeenCalledWith(
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
      const createSpy = vi
        .spyOn(apiModule, "createSourceForResource")
        .mockResolvedValue({ id: 100, source: "rmi" });

      renderCard();
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByRole("button", { name: /^edit$/i }));
      await user.click(screen.getByRole("button", { name: /add value/i }));
      await user.type(screen.getByLabelText("New value"), "Deep Basin");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(createSpy).toHaveBeenCalledWith(
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
      vi.spyOn(apiModule, "createSourceForResource").mockRejectedValue(
        new Error("overwrite failed"),
      );

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
