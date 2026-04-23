import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import "./index.css";
import App from "./App.jsx";
import AuthGate from "./auth/AuthGate";
import { ConfigProvider } from "./config/context-provider";
import { loadConfig } from "./config/env";

// Set global defaults for QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

async function bootstrap() {
  const config = await loadConfig();

  createRoot(document.getElementById("root")).render(
    <StrictMode>
      <ConfigProvider config={config}>
        <Auth0Provider
          domain={config.auth0.domain}
          clientId={config.auth0.clientId}
          authorizationParams={{
            redirect_uri: window.location.origin,
            audience: config.auth0.audience,
          }}
          useRefreshTokens={true}
        >
          <QueryClientProvider client={queryClient}>
            <AuthGate>
              <BrowserRouter>
                <App />
              </BrowserRouter>
            </AuthGate>
          </QueryClientProvider>
        </Auth0Provider>
      </ConfigProvider>
    </StrictMode>,
  );
}

bootstrap().catch((error) => {
  console.error("Failed to bootstrap app:", error);

  createRoot(document.getElementById("root")).render(
    <StrictMode>
      <div style={{ padding: "1rem", fontFamily: "sans-serif" }}>
        <h1>Configuration error</h1>
        <pre>{String(error?.message || error)}</pre>
      </div>
    </StrictMode>,
  );
});
