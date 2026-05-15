import { useAuth0 } from "@auth0/auth0-react";
import Button from "./Button";

export const LogoutButton = () => {
  const { isAuthenticated, logout: authLogout } = useAuth0();

  const logout = () =>
    authLogout({
      openUrl: () => window.location.assign(window.location.origin),
    });

  if (!isAuthenticated) {
    return null;
  }

  return (
    <Button onClick={logout} variant="secondary">
      Log out
    </Button>
  );
};
