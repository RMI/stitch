import { useEffect } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import AuthGate from "./AuthGate";

describe("AuthGate", () => {
  it("shows loading indicator while auth is loading", () => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isLoading: true,
      isAuthenticated: false,
    });

    renderWithQueryClient(
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

    renderWithQueryClient(
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

    renderWithQueryClient(
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

  describe("when a request fails", () => {
    // Shapes of the errors auth0-spa-js throws from getAccessTokenSilently, and
    // of the HTTP errors thrown by queries/api.js.
    const authError = (code) => Object.assign(new Error(code), { error: code });
    const httpError = (status) =>
      Object.assign(new Error(`HTTP error! status: ${status}`), { status });

    function FailingQuery({ error }) {
      useQuery({
        queryKey: ["failing"],
        queryFn: () => Promise.reject(error),
      });
      return null;
    }

    function FailingMutation({ error }) {
      const { mutate } = useMutation({
        mutationKey: ["failing"],
        mutationFn: () => Promise.reject(error),
      });
      useEffect(() => mutate(), [mutate]);
      return null;
    }

    let loginWithRedirect;

    beforeEach(() => {
      window.sessionStorage.clear();
      window.history.pushState({}, "", "/oil-gas-fields/1?page=2");
      loginWithRedirect = vi.fn();
      vi.mocked(useAuth0).mockReturnValue({
        ...auth0TestDefaults,
        loginWithRedirect,
      });
    });

    afterEach(() => {
      window.sessionStorage.clear();
      window.history.pushState({}, "", "/");
    });

    it.each([
      ["login_required", authError("login_required")],
      ["missing_refresh_token", authError("missing_refresh_token")],
      ["invalid_grant", authError("invalid_grant")],
      ["an API 401", httpError(401)],
    ])(
      "sends the user to log in and back to the current page on %s (STIT-848)",
      async (_label, error) => {
        renderWithQueryClient(
          <AuthGate>
            <FailingQuery error={error} />
          </AuthGate>,
        );

        await waitFor(() => expect(loginWithRedirect).toHaveBeenCalledTimes(1));
        expect(loginWithRedirect).toHaveBeenCalledWith({
          appState: { returnTo: "/oil-gas-fields/1?page=2" },
        });
      },
    );

    it("also redirects when a mutation fails for an expired session", async () => {
      renderWithQueryClient(
        <AuthGate>
          <FailingMutation error={authError("invalid_grant")} />
        </AuthGate>,
      );

      await waitFor(() => expect(loginWithRedirect).toHaveBeenCalledTimes(1));
    });

    it.each([
      ["a 403", httpError(403)],
      ["a 500", httpError(500)],
    ])("does not redirect on %s", async (_label, error) => {
      const { queryClient } = renderWithQueryClient(
        <AuthGate>
          <FailingQuery error={error} />
        </AuthGate>,
      );

      await waitFor(() =>
        expect(queryClient.getQueryState(["failing"]).status).toBe("error"),
      );
      expect(loginWithRedirect).not.toHaveBeenCalled();
    });

    it("does not redirect again soon after a redirect, so a rejected login cannot loop", async () => {
      window.sessionStorage.setItem(
        "stitch.auth.sessionRedirectAt",
        String(Date.now()),
      );

      const { queryClient } = renderWithQueryClient(
        <AuthGate>
          <FailingQuery error={httpError(401)} />
        </AuthGate>,
      );

      await waitFor(() =>
        expect(queryClient.getQueryState(["failing"]).status).toBe("error"),
      );
      expect(loginWithRedirect).not.toHaveBeenCalled();
    });
  });
});
