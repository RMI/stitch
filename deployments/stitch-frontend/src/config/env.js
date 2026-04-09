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
    appEnv:
      import.meta.env.VITE_APP_ENV || import.meta.env.MODE || "development",

    build: Object.freeze({
      appVersion: import.meta.env.VITE_APP_VERSION || "0.0.0-dev",
      buildId: import.meta.env.VITE_BUILD_ID || "local",
      gitSha: import.meta.env.VITE_GIT_SHA || "unknown",
      nodeVersion: import.meta.env.VITE_NODE_VERSION || "unknown",
      viteVersion: import.meta.env.VITE_VITE_VERSION || "unknown",
      buildTime: import.meta.env.VITE_BUILD_TIME || "unknown",
    }),
    entityLinkageBaseUrl:
      import.meta.env.VITE_ENTITY_LINKAGE_URL || "http://localhost:8001/api/v1",
  });
}

export const config = loadConfig();
export default config;
