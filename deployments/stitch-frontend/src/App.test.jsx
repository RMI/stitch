import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { useAuth0 } from "@auth0/auth0-react";
import { renderWithQueryClient } from "./test/utils";
import App from "./App";

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
      screen.getByRole("link", { name: "Entity Linkage" }),
    ).toHaveAttribute("href", "/entity-linkage");
    expect(screen.getByRole("link", { name: "Merge Review" })).toHaveAttribute(
      "href",
      "/merge-candidate-review",
    );
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});
