import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import "./index.css";
import App from "./App.jsx";
import { AuthGate } from "./AuthGate.jsx";

// Set global defaults for QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Auth0Provider
      domain="rmi-spd.us.auth0.com"
      clientId="698dba721eb165d16d533436"
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: "https://stitch-api.local",
        scope: "openid profile email",
      }}
    >
      <QueryClientProvider client={queryClient}>
        <AuthGate>
          <App />
        </AuthGate>
      </QueryClientProvider>
    </Auth0Provider>
  </StrictMode>,
);
