import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function safeExec(command) {
  try {
    return execSync(command, { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
}

function getPackageVersion() {
  try {
    const packageJsonPath = resolve(import.meta.dirname, "package.json");
    const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
    return packageJson.version ?? "0.0.0-dev";
  } catch {
    return "0.0.0-dev";
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../../", "");

  const buildMeta = {
    VITE_APP_ENV: env.VITE_APP_ENV || mode || "development",
    VITE_APP_VERSION: env.VITE_APP_VERSION || getPackageVersion(),
    VITE_BUILD_ID:
      env.VITE_BUILD_ID || safeExec("git rev-parse --short HEAD") || "local",
    VITE_GIT_SHA: env.VITE_GIT_SHA || safeExec("git rev-parse HEAD"),
    VITE_NODE_VERSION:
      env.VITE_NODE_VERSION || safeExec("node -p process.version"),
    VITE_VITE_VERSION:
      env.VITE_VITE_VERSION ||
      safeExec("npm pkg get devDependencies.vite").replace(/^"|"$/g, ""),
    VITE_BUILD_TIME: env.VITE_BUILD_TIME || new Date().toISOString(),
  };

  return {
    plugins: [react(), tailwindcss()],
    envDir: "../../",
    server: {
      port: 3000,
    },
    define: Object.fromEntries(
      Object.entries(buildMeta).map(([key, value]) => [
        `import.meta.env.${key}`,
        JSON.stringify(value),
      ]),
    ),
  };
});
