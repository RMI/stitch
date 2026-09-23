import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within, fireEvent } from "@testing-library/react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router";
import { renderWithQueryClient } from "./test/utils";
import { useResources, useResourceFilterOptions } from "./hooks/useResources";
import { usePermissions } from "./hooks/usePermissions";
import App from "./App";

vi.mock("./hooks/useResources");

const hookDefaults = {
  data: undefined,
  isLoading: false,
  isFetching: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

const FILTER_OPTION_VALUES = {
  country: ["NOR", "SAU"],
  region: ["Middle East"],
};

const mockResourceData = {
  items: [{ id: 1, data: { name: "Burgan Field", country: "NOR" } }],
  page: 1,
  page_size: 25,
  total_count: 30,
  total_pages: 2,
};

function activateCountryFilter() {
  fireEvent.click(
    within(screen.getByTestId("filter-bar")).getByRole("button", {
      name: /^country/i,
    }),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: /norway/i }));
}

function countryChip() {
  return screen.queryByRole("button", { name: "Remove Country: Norway" });
}

// Mirrors ResourceDetailPage's "← Back" (navigate(-1)). Rendered as a sibling of
// <App /> so it shares the router. window.history.back() does not drive
// MemoryRouter, so this is the way to exercise browser Back in jsdom.
function BackButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>test-back</button>;
}

vi.mock("./hooks/usePermissions");

const ALL_PERMISSIONS = [
  "resource:read",
  "resource:write",
  "source:read:rmi",
  "source:read:gem",
  "source:read:wm",
  "source:read:llm",
  "source:read:ccr",
  "source:read:bc",
  "source:read:alb",
  "source:write",
  "merge-candidate:read",
  "merge-candidate:create",
  "merge-candidate:review",
  "service:entity-linkage:run",
  "service:llm:suggest",
];

function mockPermissions({ data = [], isLoading = false } = {}) {
  vi.mocked(usePermissions).mockReturnValue({ data, isLoading });
}

describe("App", () => {
  beforeEach(() => {
    vi.mocked(useAuth0).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      error: null,
      user: { sub: "test-user-id", email: "test@example.com" },
      getAccessTokenSilently: vi.fn().mockResolvedValue("test-access-token"),
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    });
    vi.mocked(useResources).mockReturnValue({ ...hookDefaults });
    vi.mocked(useResourceFilterOptions).mockReturnValue({
      ...hookDefaults,
      data: FILTER_OPTION_VALUES,
    });
    mockPermissions({ data: ALL_PERMISSIONS });
  });

  it("renders Resources heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByRole("heading", { name: "Resources" });
    expect(heading).toBeInTheDocument();
  });

  it("does not render the single-resource fetch demo on the home route", () => {
    renderWithQueryClient(<App />);
    const heading = screen.queryByRole("heading", {
      name: /^Resource ID: \d+$/i,
    });
    expect(heading).not.toBeInTheDocument();
  });

  it("renders the normalized global shell", () => {
    renderWithQueryClient(<App />);

    expect(screen.getByRole("link", { name: /stitch/i })).toHaveAttribute(
      "href",
      "/",
    );
    expect(
      screen.getByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resources" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(
      screen.getByRole("link", { name: "Entity linkage" }),
    ).toHaveAttribute("href", "/entity-linkage");
    expect(screen.getByRole("link", { name: "Merge review" })).toHaveAttribute(
      "href",
      "/merge-candidate-review",
    );
    expect(screen.getByRole("link", { name: "ETL pipelines" })).toHaveAttribute(
      "href",
      "/etl",
    );
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  describe("logotype", () => {
    beforeEach(() => {
      vi.mocked(useResources).mockReturnValue({
        ...hookDefaults,
        data: mockResourceData,
      });
    });

    it("clears active list filters when clicked from the home route", () => {
      renderWithQueryClient(<App />);
      activateCountryFilter();
      expect(countryChip()).toBeInTheDocument();

      fireEvent.click(screen.getByRole("link", { name: /stitch/i }));

      expect(countryChip()).not.toBeInTheDocument();
    });

    it("returns to the default list view when clicked from another page", () => {
      renderWithQueryClient(<App />);
      activateCountryFilter();
      fireEvent.click(screen.getByRole("link", { name: "ETL pipelines" }));
      expect(screen.queryByTestId("filter-bar")).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("link", { name: /stitch/i }));

      expect(screen.getByTestId("filter-bar")).toBeInTheDocument();
      expect(countryChip()).not.toBeInTheDocument();
    });

    it("keeps filters when paging through the list", () => {
      renderWithQueryClient(<App />);
      activateCountryFilter();

      fireEvent.click(screen.getByRole("button", { name: "Next page" }));

      expect(countryChip()).toBeInTheDocument();
    });
  });

  describe("list state in the URL", () => {
    beforeEach(() => {
      vi.mocked(useResources).mockReturnValue({
        ...hookDefaults,
        data: {
          items: [{ id: 1, data: { name: "Burgan Field", country: "NOR" } }],
          page: 1,
          page_size: 10,
          total_count: 30,
          total_pages: 3,
        },
      });
    });

    it("reproduces a shared view from the URL alone", () => {
      renderWithQueryClient(<App />, {
        initialEntries: [
          "/?country=NOR&q=ghawar&sort_by=name&sort_order=desc&page=2",
        ],
      });

      expect(
        screen.getByRole("button", { name: "Remove Country: Norway" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Sort: Name descending")).toBeInTheDocument();
      expect(screen.getByLabelText("Search resources")).toHaveValue("ghawar");
      expect(useResources).toHaveBeenLastCalledWith(
        "oil-gas-fields",
        expect.objectContaining({
          page: 2,
          q: "ghawar",
          sort_by: "name",
          sort_order: "desc",
          filters: expect.objectContaining({ country: ["NOR"] }),
        }),
      );
    });

    it("restores the filtered list when going back", () => {
      renderWithQueryClient(
        <>
          <App />
          <BackButton />
        </>,
        { initialEntries: ["/?country=NOR", "/etl"] },
      );

      // Start away from the list, as if a resource had been opened.
      expect(screen.queryByTestId("filter-bar")).not.toBeInTheDocument();

      fireEvent.click(screen.getByText("test-back"));

      expect(
        screen.getByRole("button", { name: "Remove Country: Norway" }),
      ).toBeInTheDocument();
    });
  });

  describe("permission-gated navigation", () => {
    it("hides gated items while permissions are loading", () => {
      mockPermissions({ isLoading: true });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "Resources" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Entity linkage" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Merge review" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "ETL pipelines" }),
      ).not.toBeInTheDocument();
    });

    it("hides all gated items when the caller holds no relevant permissions", () => {
      mockPermissions({ data: [] });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "Resources" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Entity linkage" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Merge review" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "ETL pipelines" }),
      ).not.toBeInTheDocument();
    });

    it("shows Entity linkage only when the caller can run the service", () => {
      mockPermissions({ data: ["service:entity-linkage:run"] });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "Entity linkage" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Merge review" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "ETL pipelines" }),
      ).not.toBeInTheDocument();
    });

    it("shows Merge review when the caller can read merge candidates", () => {
      mockPermissions({ data: ["merge-candidate:read"] });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "Merge review" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Entity linkage" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "ETL pipelines" }),
      ).not.toBeInTheDocument();
    });

    it("shows ETL pipelines when the caller can read any source", () => {
      mockPermissions({ data: ["source:read:gem"] });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "ETL pipelines" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Entity linkage" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Merge review" }),
      ).not.toBeInTheDocument();
    });

    it("shows ETL pipelines when the caller has source:write", () => {
      mockPermissions({ data: ["source:write"] });
      renderWithQueryClient(<App />);

      expect(
        screen.getByRole("link", { name: "ETL pipelines" }),
      ).toBeInTheDocument();
    });

    it("hides Entity linkage from a caller with only read-side permissions", () => {
      mockPermissions({
        data: ["resource:read", "source:read:rmi", "merge-candidate:read"],
      });
      renderWithQueryClient(<App />);

      expect(
        screen.queryByRole("link", { name: "Entity linkage" }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Merge review" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "ETL pipelines" }),
      ).toBeInTheDocument();
    });
  });
});
