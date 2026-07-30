import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import AuthGate from "./auth/AuthGate";
import { ConfigProvider } from "./config/context-provider";

// Set global defaults for QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function AppProviders({ config, children }) {
  return (
    <ConfigProvider config={config}>
      <Auth0Provider
        domain={config.auth0.domain}
        clientId={config.auth0.clientId}
        authorizationParams={{
          redirect_uri: window.location.origin,
          audience: config.auth0.audience,
        }}
        useRefreshTokens={true}
        // Persist tokens in localStorage so the session survives a page reload
        // (STIT-581); the SDK default of in-memory storage is wiped on reload.
        // Security tradeoff: Web Storage is readable by any script on the page,
        // so this raises the impact of an XSS vulnerability. Mitigations this
        // relies on: refresh-token rotation (Auth0 tenant), a strict CSP, and
        // never injecting untrusted HTML into the DOM. Do not widen token
        // exposure (e.g. logging tokens, relaxing CSP) without revisiting this.
        cacheLocation="localstorage"
      >
        <QueryClientProvider client={queryClient}>
          <AuthGate>{children}</AuthGate>
        </QueryClientProvider>
      </Auth0Provider>
    </ConfigProvider>
  );
}
