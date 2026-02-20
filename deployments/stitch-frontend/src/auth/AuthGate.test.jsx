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
    expect(vi.mocked(useAuth0)().loginWithRedirect).not.toHaveBeenCalled();
  });

  it("shows error message when auth fails", () => {
    const loginWithRedirect = vi.fn();
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isAuthenticated: false,
      error: new Error("Something went wrong"),
      loginWithRedirect,
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
    expect(loginWithRedirect).not.toHaveBeenCalled();
  });

  it("calls loginWithRedirect when unauthenticated", () => {
    const loginWithRedirect = vi.fn();
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isAuthenticated: false,
      loginWithRedirect,
    });

    render(
      <AuthGate>
        <div>App Content</div>
      </AuthGate>,
    );

    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
    expect(loginWithRedirect).toHaveBeenCalled();
  });
});
