import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults } from "../test/utils";
import AuthGate from "./AuthGate";

describe("AuthGate", () => {
  it("shows loading indicator while auth is loading", () => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isLoading: true,
      isAuthenticated: false,
    });

    render(
      <AuthGate>
        <div>App Content</div>
      </AuthGate>,
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
  });

  it("shows error message when auth fails", () => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isAuthenticated: false,
      error: new Error("Something went wrong"),
    });

    render(
      <AuthGate>
        <div>App Content</div>
      </AuthGate>,
    );

    expect(
      screen.getByText("Authentication error: Something went wrong"),
    ).toBeInTheDocument();
    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
  });

  it("renders LoginPage when unauthenticated", () => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isAuthenticated: false,
    });

    render(
      <AuthGate>
        <div>App Content</div>
      </AuthGate>,
    );

    expect(screen.getByText("Stitch")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /log in to continue/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
  });
});
