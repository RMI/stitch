import { useAuth0 } from "@auth0/auth0-react";
import Button from "./Button";

export const LogoutButton = () => {
  const { isAuthenticated, logout: authLogout } = useAuth0();

  // Let the SDK navigate to Auth0's /v2/logout so the tenant session cookie is
  // cleared too. `returnTo` must be listed in the Auth0 application's
  // "Allowed Logout URLs" for every origin that serves the app.
  const logout = () =>
    authLogout({ logoutParams: { returnTo: window.location.origin } });

  if (!isAuthenticated) {
    return null;
  }

  return (
    <Button onClick={logout} variant="secondary">
      Log out
    </Button>
  );
};
