import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Auth0Provider } from "@auth0/auth0-react";
import "./index.css";
import App from "./App.jsx";
import { AppProviders } from "./AppProviders";
import { loadConfig } from "./config/env";
import { prewarmApi } from "./queries/prewarm";

const root = createRoot(document.getElementById("root"));

async function bootstrap() {
  const config = await loadConfig();

  // Start the API waking now, so it does so in parallel with the Auth0 redirect
  // instead of after it. Not awaited: rendering must not wait on the backend,
  // and `prewarmApi` never rejects.
  void prewarmApi(config);

  root.render(
    <StrictMode>
      <AppProviders config={config}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AppProviders>
    </StrictMode>,
  );
}

bootstrap().catch((error) => {
  console.error("Failed to bootstrap app:", error);

  root.render(
    <StrictMode>
      <div style={{ padding: "1rem", fontFamily: "sans-serif" }}>
        <h1>Configuration error</h1>
        <pre>{String(error?.message || error)}</pre>
      </div>
    </StrictMode>,
  );
});
