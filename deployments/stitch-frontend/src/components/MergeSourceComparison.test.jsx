import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MergeSourceComparison from "./MergeSourceComparison";
import { MERGE_COMPARISON_CORE_FIELDS } from "../constants/fieldMeta";

const RESOURCE_IDS = [101, 102];

function val(resourceId, value, priority) {
  return {
    source: "gem",
    source_id: priority + 1,
    value,
    priority,
    resource_id: resourceId,
  };
}

// Statuses come verbatim from the backend; the component must not re-derive
// them. "country" encodes the deliberate semantics change: case-different
// strings are now "different".
const compare = [
  {
    field: "name",
    status: "match",
    values: [val(101, "Burgan", 0), val(102, "Burgan", 1)],
  },
  {
    field: "country",
    status: "different",
    values: [val(101, "Kuwait", 0), val(102, "kuwait", 1)],
  },
  {
    field: "region",
    status: "match",
    values: [val(101, "Middle East", 0), val(102, "Middle East", 1)],
  },
  {
    field: "basin",
    status: "different",
    values: [val(101, "Arabian", 0)],
  },
  { field: "state_province", status: "match", values: [] },
  {
    field: "discovery_year",
    status: "match",
    values: [val(101, 1938, 0), val(102, 1938, 1)],
  },
];

function renderComparison(props = {}) {
  return render(
    <MergeSourceComparison
      resourceIds={RESOURCE_IDS}
      compare={compare}
      isLoading={false}
      isError={false}
      error={null}
      {...props}
    />,
  );
}

describe("MergeSourceComparison", () => {
  it("shows one column header per source resource", () => {
    renderComparison();

    expect(screen.getByText("Resource #101")).toBeInTheDocument();
    expect(screen.getByText("Resource #102")).toBeInTheDocument();
  });

  it("keeps headers and field labels in place while loading", () => {
    renderComparison({ compare: undefined, isLoading: true });

    expect(screen.getByText("Resource #101")).toBeInTheDocument();
    expect(screen.getByText("Resource #102")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Country")).toBeInTheDocument();
    expect(screen.getByText("Region")).toBeInTheDocument();
    expect(screen.getByText("Basin")).toBeInTheDocument();
    expect(screen.getByText("State / Province")).toBeInTheDocument();
    // 5 core fields x 2 sources
    expect(screen.getAllByTestId("comparison-skeleton-cell")).toHaveLength(10);
    expect(screen.getByText("Loading comparison…")).toBeInTheDocument();
  });

  it("renders backend match status on every cell", () => {
    renderComparison();

    const row = screen.getByRole("group", { name: "Name" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
  });

  it("renders case-different strings as differing, per backend status", () => {
    renderComparison();

    const row = screen.getByRole("group", { name: "Country" });
    expect(within(row).getAllByText("Differs")).toHaveLength(2);
  });

  it("grays a cell whose resource has no value and keeps backend status on the rest", () => {
    renderComparison();

    const row = screen.getByRole("group", { name: "Basin" });
    expect(within(row).getAllByText("Differs")).toHaveLength(1);
    expect(within(row).getAllByText("No value")).toHaveLength(1);
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("renders rows with no values as neutral with no judgment", () => {
    renderComparison();

    const row = screen.getByRole("group", { name: "State / Province" });
    expect(within(row).getAllByText("No value")).toHaveLength(2);
    expect(within(row).queryByText("Match")).not.toBeInTheDocument();
    expect(within(row).queryByText("Differs")).not.toBeInTheDocument();
  });

  it("treats an empty string as a real value with a real status", () => {
    renderComparison({
      compare: [
        {
          field: "name",
          status: "match",
          values: [val(101, "", 0), val(102, "", 1)],
        },
      ],
    });

    const row = screen.getByRole("group", { name: "Name" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
    expect(within(row).queryByText("No value")).not.toBeInTheDocument();
    // Nothing visible to print, so the dash is display-only.
    expect(within(row).getAllByText("—")).toHaveLength(2);
  });

  it("hides other attributes until the accordion is expanded", async () => {
    const user = userEvent.setup();
    renderComparison();

    expect(
      screen.queryByRole("group", { name: "Discovery Year" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByText("Other attributes (11)"));

    const row = screen.getByRole("group", { name: "Discovery Year" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
  });

  it("shows the most decision-relevant other attributes first", async () => {
    const user = userEvent.setup();
    renderComparison();

    await user.click(screen.getByText("Other attributes (11)"));

    const labels = screen
      .getAllByRole("group")
      .map((group) => group.getAttribute("aria-label"))
      .filter(Boolean);
    const coreLabelCount = MERGE_COMPARISON_CORE_FIELDS.length;

    expect(labels.slice(coreLabelCount, coreLabelCount + 2)).toEqual([
      "Field Status",
      "Production Start Year",
    ]);
  });

  it("shows a note when fewer than two resources", () => {
    renderComparison({ resourceIds: [101] });

    expect(
      screen.getByText(
        "At least two source resources are required to compare.",
      ),
    ).toBeInTheDocument();
  });

  it("surfaces detail load errors", () => {
    renderComparison({
      compare: undefined,
      isError: true,
      error: new Error("boom"),
    });

    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("shows a fallback when no comparison is available", () => {
    renderComparison({ compare: undefined });

    expect(screen.getByText("No comparison available.")).toBeInTheDocument();
  });
});
