const REQUIRED_KEYS = [
  "VITE_AUTH0_DOMAIN",
  "VITE_AUTH0_CLIENT_ID",
  "VITE_AUTH0_AUDIENCE",
];

function loadConfig() {
  const missing = REQUIRED_KEYS.filter((key) => !import.meta.env[key]);

  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables: ${missing.join(", ")}. ` +
        `Check your .env file or deployment config.`,
    );
  }

  return Object.freeze({
    auth0: Object.freeze({
      domain: import.meta.env.VITE_AUTH0_DOMAIN,
      clientId: import.meta.env.VITE_AUTH0_CLIENT_ID,
      audience: import.meta.env.VITE_AUTH0_AUDIENCE,
    }),
    apiBaseUrl: import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1",
  });
}

// Optional named export for `import { config } from "./config/env.js"`
export const config = loadConfig();

export default config;
