import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import AuthGate from "./auth/AuthGate";
import { ConfigProvider } from "./config/context-provider";
import { shouldRetryQuery } from "./queries/retry";

// Set global defaults for QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // Retry transient failures only -- see queries/retry.js. A single retry
      // was not enough to outlast a Container App waking from zero, and
      // retrying a 4xx only delays an error that will not change.
      retry: shouldRetryQuery,
    },
    // Mutations keep the default of no retries: they are not idempotent, so a
    // replay after a timeout could apply the same change twice.
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
        // so this raises the impact of an XSS vulnerability. It is mitigated by
        // refresh-token rotation (Auth0 tenant) and by not injecting untrusted
        // HTML into the DOM. NOTE: a Content-Security-Policy — the main defense
        // against XSS reaching this storage — is not yet in place (none in
        // staticwebapp.config.json) and is recommended hardening, tracked as a
        // follow-up. Avoid widening token exposure (e.g. logging tokens)
        // without revisiting this.
        cacheLocation="localstorage"
      >
        <QueryClientProvider client={queryClient}>
          <AuthGate>{children}</AuthGate>
        </QueryClientProvider>
      </Auth0Provider>
    </ConfigProvider>
  );
}
