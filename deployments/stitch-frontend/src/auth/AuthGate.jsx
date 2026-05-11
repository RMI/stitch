import { useAuth0 } from "@auth0/auth0-react";
import LoginPage from "../components/LoginPage";

export default function AuthGate({ children }) {
  const { isLoading, isAuthenticated, error } = useAuth0();

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
