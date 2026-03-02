import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    css: true,
    env: {
      VITE_AUTH0_DOMAIN: "test.auth0.com",
      VITE_AUTH0_CLIENT_ID: "test-client-id",
      VITE_AUTH0_AUDIENCE: "https://test-api",
      VITE_API_URL: "http://localhost:8000/api/v1",
    },
  },
});
