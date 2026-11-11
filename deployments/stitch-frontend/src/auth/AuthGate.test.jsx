import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
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

  describe("when a query fails", () => {
    function FailingQuery({ error }) {
      useQuery({
        queryKey: ["failing"],
        queryFn: () => Promise.reject(error),
      });
      return <div>App Content</div>;
    }

    // Shape of the errors auth0-spa-js throws from getAccessTokenSilently.
    const authError = (code) => Object.assign(new Error(code), { error: code });

    it("sends the user to log in when the session has expired (STIT-848)", async () => {
      const loginWithRedirect = vi.fn();
      vi.mocked(useAuth0).mockReturnValue({
        ...auth0TestDefaults,
        loginWithRedirect,
      });

      renderWithQueryClient(
        <AuthGate>
          <FailingQuery error={authError("missing_refresh_token")} />
        </AuthGate>,
      );

      await waitFor(() => expect(loginWithRedirect).toHaveBeenCalledTimes(1));
      expect(loginWithRedirect).toHaveBeenCalledWith({
        appState: { returnTo: "/" },
      });
    });

    it("does not redirect for other failures", async () => {
      const loginWithRedirect = vi.fn();
      vi.mocked(useAuth0).mockReturnValue({
        ...auth0TestDefaults,
        loginWithRedirect,
      });
      const httpError = Object.assign(new Error("HTTP error! status: 500"), {
        status: 500,
      });
      let failed;
      const failedPromise = new Promise((resolve) => (failed = resolve));
      function Probe() {
        const { isError } = useQuery({
          queryKey: ["failing"],
          queryFn: () => Promise.reject(httpError),
        });
        if (isError) failed();
        return null;
      }

      renderWithQueryClient(
        <AuthGate>
          <Probe />
        </AuthGate>,
      );

      await failedPromise;
      expect(loginWithRedirect).not.toHaveBeenCalled();
    });
  });
});
