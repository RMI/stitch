import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithQueryClient } from "../test/utils";
import MergedResourceView from "./MergedResourceView";
import { getResourceDetail } from "../queries/api";

vi.mock("../queries/api", () => ({
  getResourceDetail: vi.fn(),
}));

const mergedDetail = {
  data: {
    name: "Burgan Consolidated",
    country: "Kuwait",
    region: "Middle East",
    basin: "Arabian",
    state_province: null,
    discovery_year: 1938,
  },
};

function renderMergedView(resourceId = 201) {
  return renderWithQueryClient(
    <MergedResourceView endpoint="oil-gas-fields" resourceId={resourceId} />,
  );
}

describe("MergedResourceView", () => {
  it("shows a loading message while the merged resource loads", () => {
    vi.mocked(getResourceDetail).mockReturnValue(new Promise(() => {}));
    renderMergedView();

    expect(screen.getByText("Loading merged resource…")).toBeInTheDocument();
  });

  it("renders merged core field values", async () => {
    vi.mocked(getResourceDetail).mockResolvedValue(mergedDetail);
    renderMergedView();

    const row = await screen.findByRole("group", { name: "Name" });
    expect(within(row).getByText("Burgan Consolidated")).toBeInTheDocument();
  });

  it("shows a dash for unset fields", async () => {
    vi.mocked(getResourceDetail).mockResolvedValue(mergedDetail);
    renderMergedView();

    const row = await screen.findByRole("group", {
      name: "State / Province",
    });
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("hides other attributes until the accordion is expanded", async () => {
    const user = userEvent.setup();
    vi.mocked(getResourceDetail).mockResolvedValue(mergedDetail);
    renderMergedView();

    await screen.findByRole("group", { name: "Name" });
    expect(
      screen.queryByRole("group", { name: "Discovery Year" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByText("Other attributes (11)"));

    const row = screen.getByRole("group", { name: "Discovery Year" });
    expect(within(row).getByText("1938")).toBeInTheDocument();
  });

  it("surfaces fetch errors", async () => {
    vi.mocked(getResourceDetail).mockRejectedValue(new Error("boom"));
    renderMergedView();

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});
