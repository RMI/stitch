import { useAuth0 } from "@auth0/auth0-react";

export function AuthGate({ children }) {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0();

  if (isLoading) return <div role="status" aria-live="polite">Loading…</div>;

  if (!isAuthenticated) {
    return (
      <div style={{ padding: 16 }}>
        <button onClick={() => loginWithRedirect()}>Log in to Stitch</button>
      </div>
    );
  }

  return children;
}
