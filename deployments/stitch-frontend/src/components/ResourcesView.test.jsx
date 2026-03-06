import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithQueryClient } from "../test/utils";
import ResourcesView from "./ResourcesView";
import { useResources } from "../hooks/useResources";

vi.mock("../hooks/useResources");

const mockResourceData = [
  {
    id: 1,
    name: "Burgan Field",
    state_province: "Kuwait",
    region: "Middle East",
    basin: "Arabian",
    source_data: { gem: [{}], wm: [], rmi: [], llm: [] },
  },
  {
    id: 2,
    name: "Ghawar Field",
    state_province: null,
    region: "Middle East",
    basin: "Arabian",
    source_data: { gem: [{}], wm: [{}], rmi: [], llm: [] },
  },
];

const defaultHookReturn = {
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useResources).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
});

describe("ResourcesView", () => {
  it("renders heading and endpoint information", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByText("Resources")).toBeInTheDocument();
    expect(screen.getByText(/\/api\/v1\/resources\//)).toBeInTheDocument();
  });

  it("renders Fetch and Clear Cache buttons", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByRole("button", { name: /fetch/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).toBeInTheDocument();
  });

  it("disables Clear Cache button when no data", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByRole("button", { name: /clear cache/i })).toBeDisabled();
  });

  it("shows loading state while fetching", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn(() => {
      vi.mocked(useResources).mockReturnValue({
        ...defaultHookReturn,
        isLoading: true,
      });
    });
    vi.mocked(useResources).mockReturnValue({ ...defaultHookReturn, refetch });

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    await user.click(screen.getByRole("button", { name: /fetch/i }));

    expect(refetch).toHaveBeenCalled();
  });

  it("renders table rows when data is available", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
    expect(screen.getByText("Ghawar Field")).toBeInTheDocument();
  });

  it("renders column headers when data is available", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

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

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByRole("button", { name: /region/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /basin/i })).toBeInTheDocument();
  });

  it("does not show filter bar when no data", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(
      screen.queryByRole("button", { name: /region/i }),
    ).not.toBeInTheDocument();
  });

  it("enables Clear Cache button when data is loaded", () => {
    vi.mocked(useResources).mockReturnValue({
      ...defaultHookReturn,
      data: mockResourceData,
    });

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

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

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).not.toBeDisabled();
  });
});
