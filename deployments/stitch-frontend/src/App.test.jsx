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
    const heading = screen.getByText(/^Resources$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders Resource heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByText(/^Resource ID: \d+$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders both ResourcesView and ResourceView components", () => {
    renderWithQueryClient(<App />);

    expect(screen.getByText(/^Resources$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Resource ID: \d+$/i)).toBeInTheDocument();
  });
});
