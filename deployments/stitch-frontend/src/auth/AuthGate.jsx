import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import LoginPage from "../components/LoginPage";

// Auth0 error codes meaning the stored session can no longer produce tokens
// (e.g. the refresh token expired). The SDK still reports `isAuthenticated`
// from the cached user, so without handling these every request fails while
// the app looks logged in (STIT-848). `login_required` only comes from the
// SDK's iframe fallback, which is not enabled (`useRefreshTokensFallback`); it
// is listed so enabling the fallback stays covered.
const SESSION_EXPIRED_ERRORS = new Set([
  "login_required",
  "missing_refresh_token",
  "invalid_grant",
]);

// The API answers 401 for a missing, invalid or expired token, so logging in
// again usually fixes it. If the API rejects every token (e.g. an audience
// mismatch, or it cannot reach Auth0's signing keys), logging in again cannot
// help and would loop. So at most one redirect is attempted per tab within this
// window; after that, the failed request's error shows instead.
const REDIRECT_GUARD_KEY = "stitch.auth.sessionRedirectAt";
const REDIRECT_GUARD_MS = 5 * 60_000;

function isSessionExpired(error) {
  return SESSION_EXPIRED_ERRORS.has(error?.error) || error?.status === 401;
}

// Records a redirect, or returns false if one happened within the guard window.
// Without storage the loop guard cannot work, so no redirect is attempted.
function claimRedirect() {
  try {
    const last = Number(window.sessionStorage.getItem(REDIRECT_GUARD_KEY));
    if (last && Date.now() - last < REDIRECT_GUARD_MS) return false;
    window.sessionStorage.setItem(REDIRECT_GUARD_KEY, String(Date.now()));
    return true;
  } catch {
    return false;
  }
}

export default function AuthGate({ children }) {
  const { isLoading, isAuthenticated, error, loginWithRedirect } = useAuth0();
  const queryClient = useQueryClient();

  // Send the user to log in when a query or mutation fails for an expired
  // session, and return them to the current page afterwards (the SDK's default
  // redirect callback restores `appState.returnTo`).
  useEffect(() => {
    let redirecting = false;
    function handleCacheEvent(event) {
      if (
        redirecting ||
        event.type !== "updated" ||
        event.action.type !== "error" ||
        !isSessionExpired(event.action.error)
      ) {
        return;
      }
      redirecting = true;
      if (!claimRedirect()) return;
      loginWithRedirect({
        appState: {
          returnTo: window.location.pathname + window.location.search,
        },
      });
    }
    const unsubscribeQueries = queryClient
      .getQueryCache()
      .subscribe(handleCacheEvent);
    const unsubscribeMutations = queryClient
      .getMutationCache()
      .subscribe(handleCacheEvent);
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
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
