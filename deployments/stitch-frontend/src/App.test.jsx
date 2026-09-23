import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { useAuth0 } from "@auth0/auth0-react";
import { renderWithQueryClient } from "./test/utils";
import { usePermissions } from "./hooks/usePermissions";
import App from "./App";

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
