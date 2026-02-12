import { useAuth0 } from "@auth0/auth0-react";

export function AuthGate({ children }) {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0();

  if (isLoading) return <div>Loading…</div>;

  if (!isAuthenticated) {
    return (
      <div style={{ padding: 16 }}>
        <button onClick={() => loginWithRedirect()}>Log in</button>
      </div>
    );
  }

  return children;
}
