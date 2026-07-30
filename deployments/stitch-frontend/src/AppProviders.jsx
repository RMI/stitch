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
        cacheLocation="localstorage"
      >
        <QueryClientProvider client={queryClient}>
          <AuthGate>{children}</AuthGate>
        </QueryClientProvider>
      </Auth0Provider>
    </ConfigProvider>
  );
}
