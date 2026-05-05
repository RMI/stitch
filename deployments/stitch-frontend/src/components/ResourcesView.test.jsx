import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within, fireEvent } from "@testing-library/react";
import { renderWithQueryClient } from "../test/utils";
import ResourcesView from "./ResourcesView";
import { useResources } from "../hooks/useResources";
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE } from "../queries/resources";

vi.mock("../hooks/useResources");

const mockItems = [
  {
    id: 1,
    data: {
      name: "Burgan Field",
      state_province: "Kuwait",
      region: "Middle East",
      basin: "Arabian",
    },
    provenance: {
      name: "gem",
      state_province: "gem",
      region: "wm",
      basin: "wm",
    },
  },
  {
    id: 2,
    data: {
      name: "Ghawar Field",
      state_province: null,
      region: "Middle East",
      basin: "Arabian",
    },
    provenance: {
      name: "gem",
      region: "wm",
      basin: "wm",
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
  isError: false,
  error: null,
};

beforeEach(() => {
  vi.mocked(useResources).mockReturnValue({
    ...defaultHookReturn,
  });
});

describe("ResourcesView", () => {
  const ENDPOINT = "oil-gas-fields";

  it("renders heading and endpoint information", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByText("Resources")).toBeInTheDocument();
    expect(screen.getByText(new RegExp(ENDPOINT))).toBeInTheDocument();
  });

  it("renders search and Clear Cache controls", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByRole("searchbox", { name: /search resources/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).toBeInTheDocument();
  });

  it("disables Clear Cache button when no data", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByRole("button", { name: /clear cache/i })).toBeDisabled();
  });

  it("shows loading state while fetching", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      isLoading: true,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.getByText("Loading resources...")).toBeInTheDocument();
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

    expect(screen.getByText("Name")).toBeInTheDocument();
    // "Basin" appears in both the filter bar and the table header
    expect(screen.getAllByText("Basin").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Data source mix")).toBeInTheDocument();
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
  });

  it("does not show filter bar when no data", () => {
    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(screen.queryByTestId("filter-bar")).not.toBeInTheDocument();
  });

  it("enables Clear Cache button when data is loaded", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).not.toBeDisabled();
  });

  it("enables Clear Cache button when in error state", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      isError: true,
      error: new Error("HTTP error! status: 500"),
    });

    renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).not.toBeDisabled();
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

    it("resets pagination to page 1 when sorting changes", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 30 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.click(screen.getByLabelText("Next page"));
      const table = screen.getByRole("table");
      fireEvent.click(within(table).getByRole("button", { name: /^basin/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          page: DEFAULT_PAGE,
          sort_by: "basin",
          sort_order: "asc",
        }),
      );
    });
  });

  describe("filtering", () => {
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

    it("resets pagination to page 1 when filters change", () => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        data: { ...mockResourceData, total_pages: 3, total_count: 30 },
      });

      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.click(screen.getByLabelText("Next page"));
      fireEvent.click(
        within(screen.getByTestId("filter-bar")).getByRole("button", {
          name: /region/i,
        }),
      );
      fireEvent.click(screen.getByRole("checkbox", { name: /middle east/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          page: DEFAULT_PAGE,
          filters: expect.objectContaining({ region: ["Middle East"] }),
        }),
      );
    });

    it("resets filters when Clear Cache is clicked", () => {
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
      fireEvent.click(screen.getByRole("button", { name: /clear cache/i }));

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          filters: expect.objectContaining({
            region: [],
            basin: [],
            state_province: [],
          }),
        }),
      );
    });
  });

  describe("search", () => {
    it("passes q to useResources when search text changes", () => {
      renderWithQueryClient(<ResourcesView endpoint={ENDPOINT} />);

      fireEvent.change(
        screen.getByRole("searchbox", { name: /search resources/i }),
        {
          target: { value: "ghawar" },
        },
      );

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({ q: "ghawar" }),
      );
    });

    it("resets pagination to page 1 when search text changes", () => {
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

      expect(useResources).toHaveBeenLastCalledWith(
        ENDPOINT,
        expect.objectContaining({
          page: DEFAULT_PAGE,
          q: "ghawar",
        }),
      );
    });
  });
});
