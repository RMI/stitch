import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import MergeSourceComparison from "./MergeSourceComparison";
import { getResourceDetail } from "../queries/api";

vi.mock("../queries/api", () => ({
  getResourceDetail: vi.fn(),
}));

const detailsById = {
  101: {
    data: {
      name: "Burgan",
      country: "Kuwait",
      region: "Middle East",
      basin: "Arabian",
      state_province: null,
      discovery_year: 1938,
    },
  },
  102: {
    data: {
      name: "Burgan",
      country: "kuwait",
      region: "Middle East",
      basin: null,
      state_province: null,
      discovery_year: 1938,
    },
  },
};

function renderComparison(resourceIds = [101, 102]) {
  return renderWithQueryClient(
    <MergeSourceComparison
      endpoint="oil-gas-fields"
      resourceIds={resourceIds}
    />,
  );
}

describe("MergeSourceComparison", () => {
  beforeEach(() => {
    vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
    vi.mocked(getResourceDetail).mockImplementation((_config, id) =>
      Promise.resolve(detailsById[id]),
    );
  });

  it("shows one column header per source resource", async () => {
    renderComparison();

    expect(await screen.findByText("Resource #101")).toBeInTheDocument();
    expect(screen.getByText("Resource #102")).toBeInTheDocument();
  });

  it("keeps headers and field labels in place while sources load", () => {
    vi.mocked(getResourceDetail).mockReturnValue(new Promise(() => {}));
    renderComparison();

    expect(screen.getByText("Resource #101")).toBeInTheDocument();
    expect(screen.getByText("Resource #102")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Country")).toBeInTheDocument();
    expect(screen.getByText("Region")).toBeInTheDocument();
    expect(screen.getByText("Basin")).toBeInTheDocument();
    expect(screen.getByText("State / Province")).toBeInTheDocument();
  });

  it("shows a placeholder cell per source for every field while loading", () => {
    vi.mocked(getResourceDetail).mockReturnValue(new Promise(() => {}));
    renderComparison();

    // 5 core fields x 2 sources
    expect(screen.getAllByTestId("comparison-skeleton-cell")).toHaveLength(10);
  });

  it("announces the loading state to screen readers", () => {
    vi.mocked(getResourceDetail).mockReturnValue(new Promise(() => {}));
    renderComparison();

    expect(screen.getByText("Loading source resources…")).toBeInTheDocument();
  });

  it("marks agreeing values as matches on every cell", async () => {
    renderComparison();

    const row = await screen.findByRole("group", { name: "Name" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
  });

  it("marks case-different string values as matches", async () => {
    renderComparison();

    const row = await screen.findByRole("group", { name: "Country" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
  });

  it("grays the empty cell and marks the populated one as differing", async () => {
    renderComparison();

    const row = await screen.findByRole("group", { name: "Basin" });
    expect(within(row).getAllByText("Differs")).toHaveLength(1);
    expect(within(row).getAllByText("No value")).toHaveLength(1);
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("renders all-empty rows as neutral with no judgment", async () => {
    renderComparison();

    const row = await screen.findByRole("group", {
      name: "State / Province",
    });
    expect(within(row).getAllByText("No value")).toHaveLength(2);
    expect(within(row).queryByText("Match")).not.toBeInTheDocument();
    expect(within(row).queryByText("Differs")).not.toBeInTheDocument();
  });

  it("hides other attributes until the accordion is expanded", async () => {
    const user = userEvent.setup();
    renderComparison();

    // "Burgan" is a fetched value, so it only appears once the sources load.
    // Headers render during loading and are no longer a loaded signal.
    await screen.findAllByText("Burgan");
    expect(
      screen.queryByRole("group", { name: "Discovery Year" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByText("Other attributes (11)"));

    const row = screen.getByRole("group", { name: "Discovery Year" });
    expect(within(row).getAllByText("Match")).toHaveLength(2);
  });

  it("shows a note instead of fetching when fewer than two resources", () => {
    renderComparison([101]);

    expect(
      screen.getByText(
        "At least two source resources are required to compare.",
      ),
    ).toBeInTheDocument();
    expect(getResourceDetail).not.toHaveBeenCalled();
  });

  it("surfaces fetch errors", async () => {
    vi.mocked(getResourceDetail).mockRejectedValue(new Error("boom"));
    renderComparison();

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});
