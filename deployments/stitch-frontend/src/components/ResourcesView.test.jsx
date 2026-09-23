import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within, fireEvent } from "@testing-library/react";
import { useNavigate } from "react-router";
import { renderWithQueryClient } from "../test/utils";
import ResourcesView from "./ResourcesView";
import { useResourceFilterOptions, useResources } from "../hooks/useResources";
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE } from "../queries/resources";

vi.mock("../hooks/useResources");

const mockItems = [
  {
    id: 1,
    data: {
      name: "Burgan Field",
      country: "NOR",
      state_province: "Kuwait",
      region: "Middle East",
      basin: "Arabian",
      field_status: "Producing",
      primary_hydrocarbon_group: "Oil",
    },
    provenance: {
      name: "gem",
      country: "gem",
      state_province: "gem",
      region: "wm",
      basin: "wm",
      field_status: "gem",
    },
  },
  {
    id: 2,
    data: {
      name: "Ghawar Field",
      country: "SAU",
      state_province: null,
      region: "Middle East",
      basin: "Arabian",
      field_status: "Producing",
      primary_hydrocarbon_group: "Oil",
    },
    provenance: {
      name: "gem",
      country: "gem",
      region: "wm",
      basin: "wm",
      field_status: "gem",
    },
  },
];

const mockResourceData = {
  items: mockItems,
  page: DEFAULT_PAGE,
  page_size: DEFAULT_PAGE_SIZE,
  total_count: 2,
  total_pages: 1,
};

const defaultHookReturn = {
  data: undefined,
  isLoading: false,
  isFetching: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useResources).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
  vi.mocked(useResourceFilterOptions).mockReturnValue({
    ...defaultHookReturn,
    data: {
      region: ["Middle East"],
      basin: ["Arabian", "Permian"],
      state_province: ["Kuwait"],
      field_status: ["Producing"],
      country: ["NOR", "SAU"],
      primary_hydrocarbon_group: ["Oil", "Gas"],
    },
  });
});

// Mirrors ResourceDetailPage's "← Back" (navigate(-1)). Rendered as a sibling of
// <ResourcesView /> so it shares the router. window.history.back() does not
// drive MemoryRouter, so this is the way to exercise browser Back in jsdom.
function BackButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>test-back</button>;
}

describe("ResourcesView", () => {
  const ENDPOINT = "oil-gas-fields";

  it("renders heading and keeps endpoint information in diagnostics", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByText("Resources")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics")).toBeInTheDocument();
    expect(screen.getByText(new RegExp(ENDPOINT))).toBeInTheDocument();
  });

  it("renders the refresh control", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByRole("button", { name: /refresh/i }),
    ).toBeInTheDocument();
  });

  it("renders search controls", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByRole("searchbox", { name: /search resources/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^search$/i }),
    ).toBeInTheDocument();
  });

  it("shows loading state while refreshing", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      isLoading: true,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    const refreshButton = screen.getByRole("button", { name: /refreshing/i });
    expect(refreshButton).toBeInTheDocument();
    expect(refreshButton).toBeDisabled();
    expect(screen.getByText(/loading resources/i)).toBeInTheDocument();
  });

  it("calls refetch when Refresh is clicked", () => {
    const refetch = vi.fn();
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
      refetch,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    expect(refetch).toHaveBeenCalled();
  });

  it("renders table rows when data is available", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
    expect(screen.getByText("Ghawar Field")).toBeInTheDocument();
  });

  it("renders column headers when data is available", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    const table = screen.getByRole("table");
    expect(
      within(table).getByRole("button", { name: /^name/i }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("button", { name: /^basin/i }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("button", { name: /^field status/i }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("button", { name: /^country/i }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("button", {
        name: /^primary hydrocarbon group/i,
      }),
    ).toBeInTheDocument();
    expect(within(table).getByText("Data source mix")).toBeInTheDocument();
  });

  it("renders country as a conventional name rather than the alpha-3 code", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    const table = screen.getByRole("table");
    expect(within(table).getByText("Norway")).toBeInTheDocument();
    expect(within(table).getByText("Saudi Arabia")).toBeInTheDocument();
    // The raw codes should not be shown in the table.
    expect(within(table).queryByText("NOR")).not.toBeInTheDocument();
    expect(within(table).queryByText("SAU")).not.toBeInTheDocument();
  });

  it("shows filter bar when data is available", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    const filterBar = screen.getByTestId("filter-bar");
    expect(
      within(filterBar).getByRole("button", { name: /region/i }),
    ).toBeInTheDocument();
    expect(
      within(filterBar).getByRole("button", { name: /basin/i }),
    ).toBeInTheDocument();
    expect(
      within(filterBar).getByRole("button", { name: /field status/i }),
    ).toBeInTheDocument();
  });

  it("shows filter bar even before any data has loaded", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByTestId("filter-bar")).toBeInTheDocument();
  });

  it("keeps filter bar visible while a new query is loading", () => {
    // Mirrors a refetch triggered by a filter change: TanStack Query resets
    // `data` to undefined and `isLoading` to true for the new query key.
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: undefined,
      isLoading: true,
      isFetching: true,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByTestId("filter-bar")).toBeInTheDocument();
  });

  it("keeps showing the previous data (assets count, rows) during a background refetch", () => {
    // With placeholderData: keepPreviousData on the query, a refetch
    // triggered by a filter/page/sort change keeps `data` populated:
    // isFetching is true but isLoading is false, and data is still the
    // previous result rather than resetting to undefined.
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
      isLoading: false,
      isFetching: true,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByText((_, node) => {
        if (!node || node.tagName !== "P") return false;
        return (
          node.textContent?.replace(/\s+/g, " ").trim() ===
          `${mockResourceData.total_count} assets`
        );
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/awaiting resource count/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
  });

  it("shows filter bar when the current result set is empty", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: { ...mockResourceData, items: [], total_count: 0 },
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByTestId("filter-bar")).toBeInTheDocument();
  });

  describe("pagination", () => {
    it("does not render pagination when only one page", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(screen.queryByLabelText("Previous page")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Next page")).not.toBeInTheDocument();
    });

    it("renders pagination when multiple pages exist", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 5, total_count: 250 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(screen.getByLabelText("Previous page")).toBeInTheDocument();
      expect(screen.getByLabelText("Next page")).toBeInTheDocument();
    });

    it("keeps pagination visible during a background refetch", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 150 },
        isLoading: false,
        isFetching: true,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(screen.getByLabelText("Previous page")).toBeInTheDocument();
      expect(screen.getByLabelText("Next page")).toBeInTheDocument();
    });

    it("disables previous button on first page", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 150 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(screen.getByLabelText("Previous page")).toBeDisabled();
      expect(screen.getByLabelText("Next page")).not.toBeDisabled();
    });

    it("shows correct item range", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 150 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(
        screen.getByText(`Showing 1–${DEFAULT_PAGE_SIZE} of 150`),
      ).toBeInTheDocument();
    });

    it("renders page size selector", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 150 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(screen.getByLabelText("Per page:")).toBeInTheDocument();
    });

    it("calls useResources with page, page_size, filters, and sort params", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(useResources).toHaveBeenCalledWith(
        ENDPOINT,
        expect.objectContaining({
          page: DEFAULT_PAGE,
          page_size: DEFAULT_PAGE_SIZE,
          enabled: true,
          filters: expect.any(Object),
          q: undefined,
          sort_by: undefined,
          sort_order: undefined,
        }),
      );
    });

    it("passes updated page_size to useResources when changed", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 150 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.change(screen.getByLabelText("Per page:"), {
        target: { value: "25" },
      });

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ page: DEFAULT_PAGE, page_size: 25 }),
      );
    });
  });

  describe("sorting", () => {
    it("passes sort_by and sort_order to useResources when a column header is clicked", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      // scope to the table to avoid matching the FilterBar's Basin dropdown button
      const table = screen.getByRole("table");
      fireEvent.click(within(table).getByRole("button", { name: /^basin/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ sort_by: "basin", sort_order: "asc" }),
      );
    });

    it("toggles sort_order to desc on second click of same column", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const table = screen.getByRole("table");
      fireEvent.click(within(table).getByRole("button", { name: /^basin/i }));
      fireEvent.click(within(table).getByRole("button", { name: /^basin/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ sort_by: "basin", sort_order: "desc" }),
      );
    });

    it("sorts by the country column", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const table = screen.getByRole("table");
      fireEvent.click(within(table).getByRole("button", { name: /^country/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ sort_by: "country", sort_order: "asc" }),
      );
    });
  });

  describe("filtering", () => {
    it("renders the view described by the URL", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />, {
        initialEntries: ["/?country=NOR&q=ghawar&sort_by=name&sort_order=desc"],
      });

      expect(
        screen.getByRole("button", { name: "Remove Country: Norway" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Sort: Name descending")).toBeInTheDocument();
      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          filters: expect.objectContaining({ country: ["NOR"] }),
          q: "ghawar",
          sort_by: "name",
          sort_order: "desc",
        }),
      );
    });

    it("loads every dropdown's options from a single filter-options query", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(useResourceFilterOptions).toHaveBeenCalledTimes(1);
      expect(useResourceFilterOptions).toHaveBeenCalledWith(ENDPOINT);
    });

    it("shows country options as conventional names but filters by the code", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      // Open the Country dropdown (scoped to the filter bar).
      fireEvent.click(
        within(screen.getByTestId("filter-bar")).getByRole("button", {
          name: /^country/i,
        }),
      );

      // The option is labelled with the conventional name...
      const option = screen.getByRole("checkbox", { name: /norway/i });
      fireEvent.click(option);

      // ...but the value sent to the API is the alpha-3 code.
      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          filters: expect.objectContaining({ country: ["NOR"] }),
        }),
      );
    });

    it("lists country options alphabetically by displayed name", () => {
      // The API returns values sorted by the stored alpha-3 code, which is not
      // the same order as the country names the user actually sees.
      vi.mocked(useResourceFilterOptions).mockReturnValue({
        ...defaultHookReturn,
        data: {
          region: [],
          basin: [],
          state_province: [],
          field_status: [],
          country: ["CHN", "DEU", "DNK"],
          primary_hydrocarbon_group: [],
        },
      });
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const filterBar = screen.getByTestId("filter-bar");
      fireEvent.click(
        within(filterBar).getByRole("button", { name: /^country/i }),
      );

      const labels = within(filterBar)
        .getAllByRole("checkbox")
        .map((checkbox) => checkbox.closest("label").textContent.trim());
      expect(labels).toEqual(["China", "Denmark", "Germany"]);
    });

    it("passes active filters to useResources", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      // open the Region dropdown and check "Middle East"
      fireEvent.click(
        within(screen.getByTestId("filter-bar")).getByRole("button", {
          name: /region/i,
        }),
      );
      fireEvent.click(screen.getByRole("checkbox", { name: /middle east/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          filters: expect.objectContaining({ region: ["Middle East"] }),
        }),
      );
    });

    it("resets filters when Clear all is clicked", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.click(
        within(screen.getByTestId("filter-bar")).getByRole("button", {
          name: /region/i,
        }),
      );
      fireEvent.click(screen.getByRole("checkbox", { name: /middle east/i }));
      fireEvent.click(screen.getByRole("button", { name: /clear all/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          filters: expect.objectContaining({
            region: [],
            basin: [],
            state_province: [],
            field_status: [],
          }),
        }),
      );
    });
  });

  describe("search", () => {
    it("does not call useResources with q while typing before submit", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      vi.mocked(useResources).mockClear();

      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        {
          target: { value: "ghawar" },
        },
      );

      const callsWithQ = vi
        .mocked(useResources)
        .mock.calls.filter(([, params]) => params?.q !== undefined);
      expect(callsWithQ).toHaveLength(0);
    });

    it("passes q to useResources when Search is clicked", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        {
          target: { value: "ghawar" },
        },
      );
      fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: "ghawar" }),
      );
    });

    it("passes q to useResources when Enter submits the search form", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const input = screen.getByRole("searchbox", {
        name: /search resources/i,
      });
      fireEvent.change(input, { target: { value: "ghawar" } });
      fireEvent.submit(input.closest("form"));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: "ghawar" }),
      );
    });

    it("trims whitespace before submitting", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        { target: { value: "  ghawar  " } },
      );
      fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: "ghawar" }),
      );
    });

    it("resets pagination to page 1 when search is submitted", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 30 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.click(screen.getByLabelText("Next page"));
      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        {
          target: { value: "ghawar" },
        },
      );
      fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          page: DEFAULT_PAGE,
          q: "ghawar",
        }),
      );
    });

    it("does not show the clear search button when the input is empty", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      expect(
        screen.queryByRole("button", { name: /clear search/i }),
      ).not.toBeInTheDocument();
    });

    it("shows the clear search button when the input has text", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        { target: { value: "g" } },
      );

      expect(
        screen.getByRole("button", { name: /clear search/i }),
      ).toBeInTheDocument();
    });

    it("clears the active search when the input is emptied", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const input = screen.getByRole("searchbox", {
        name: /search resources/i,
      });
      fireEvent.change(input, { target: { value: "ghawar" } });
      fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: "ghawar" }),
      );

      fireEvent.change(input, { target: { value: "" } });

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: undefined }),
      );
    });

    it("re-seeds the search box when the URL's q changes underneath it", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: mockResourceData,
      });

      renderWithQueryClient(
        <>
          <ResourcesView endpoint={ENDPOINT} />
          <BackButton />
        </>,
        { initialEntries: ["/?q=alpha", "/?q=beta"] },
      );

      expect(screen.getByLabelText("Search resources")).toHaveValue("beta");

      fireEvent.click(screen.getByText("test-back"));

      expect(screen.getByLabelText("Search resources")).toHaveValue("alpha");
    });

    it("clears the input and active search when Clear search is clicked", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      const input = screen.getByRole("searchbox", {
        name: /search resources/i,
      });
      fireEvent.change(input, { target: { value: "ghawar" } });
      fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

      fireEvent.click(screen.getByRole("button", { name: /clear search/i }));

      expect(input).toHaveValue("");
      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: undefined }),
      );
    });
  });
});
