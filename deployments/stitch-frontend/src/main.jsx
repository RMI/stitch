import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.jsx";
import { AppProviders } from "./AppProviders";
import { loadConfig } from "./config/env";

const root = createRoot(document.getElementById("root"));

async function bootstrap() {
  const config = await loadConfig();

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
