import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import LoginPage from "../components/LoginPage";

// Auth0 error codes meaning the stored session can no longer produce tokens
// (e.g. the refresh token expired). The SDK still reports `isAuthenticated`
// from the cached user, so without handling these every request fails while
// the app looks logged in (STIT-848).
const SESSION_EXPIRED_ERRORS = new Set([
  "login_required",
  "missing_refresh_token",
  "invalid_grant",
]);

export default function AuthGate({ children }) {
  const { isLoading, isAuthenticated, error, loginWithRedirect } = useAuth0();
  const queryClient = useQueryClient();

  // Send the user to log in when a query fails for an expired session, and
  // return them to the current page afterwards (the SDK's default redirect
  // callback restores `appState.returnTo`).
  useEffect(() => {
    let redirecting = false;
    return queryClient.getQueryCache().subscribe((event) => {
      if (
        !redirecting &&
        event.type === "updated" &&
        event.action.type === "error" &&
        SESSION_EXPIRED_ERRORS.has(event.action.error?.error)
      ) {
        redirecting = true;
        loginWithRedirect({
          appState: {
            returnTo: window.location.pathname + window.location.search,
          },
        });
      }
    });
  }, [queryClient, loginWithRedirect]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <p className="text-lg text-ink-muted">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <p className="text-lg text-danger">
          Authentication error: {error.message}
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return children;
}
