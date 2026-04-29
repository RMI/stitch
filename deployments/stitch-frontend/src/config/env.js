let resolvedConfig = null;
let configPromise = null;

const REQUIRED_CONFIG_KEYS = [
  "appEnv",
  "auth0Domain",
  "auth0ClientId",
  "auth0Audience",
];
const OPTIONAL_STRING_CONFIG_KEYS = [
  "apiUrl",
  "entityLinkageUrl",
  "stitchLlmUrl",
];

const DEFAULT_CONFIG_PATH = "/config.json";

function validateStringValue(config, key, { required = false } = {}) {
  const value = config[key];

  if (value == null || value === "") {
    if (required) {
      throw new Error(`Missing required runtime config values: ${key}.`);
    }
    return "";
  }

  if (typeof value !== "string") {
    throw new Error(`Runtime config value "${key}" must be a string.`);
  }

  const normalizedValue = value.trim();
  if (!normalizedValue) {
    if (required) {
      throw new Error(`Missing required runtime config values: ${key}.`);
    }
    return "";
  }

  return normalizedValue;
}

function freezeConfig(runtimeConfig) {
  return Object.freeze({
    auth0: Object.freeze({
      domain: runtimeConfig.auth0Domain,
      clientId: runtimeConfig.auth0ClientId,
      audience: runtimeConfig.auth0Audience,
    }),
    apiBaseUrl: runtimeConfig.apiUrl || "http://localhost:8000/api/v1",
    appEnv: runtimeConfig.appEnv,
    build: Object.freeze({
      appVersion: import.meta.env.VITE_APP_VERSION || "0.0.0-dev",
      buildId: import.meta.env.VITE_BUILD_ID || "local",
      gitSha: import.meta.env.VITE_GIT_SHA || "unknown",
      nodeVersion: import.meta.env.VITE_NODE_VERSION || "unknown",
      viteVersion: import.meta.env.VITE_VITE_VERSION || "unknown",
      buildTime: import.meta.env.VITE_BUILD_TIME || "unknown",
    }),
    entityLinkageBaseUrl:
      runtimeConfig.entityLinkageUrl || "http://localhost:8001/api/v1",
    stitchLlmBaseUrl:
      runtimeConfig.stitchLlmUrl || "http://localhost:8002/api/v1",
  });
}

function validateRuntimeConfig(config) {
  if (!config || typeof config !== "object") {
    throw new Error("Runtime config is missing or invalid.");
  }

  const normalizedConfig = Object.fromEntries(
    REQUIRED_CONFIG_KEYS.map((key) => [
      key,
      validateStringValue(config, key, { required: true }),
    ]),
  );

  for (const key of OPTIONAL_STRING_CONFIG_KEYS) {
    normalizedConfig[key] = validateStringValue(config, key);
  }

  return normalizedConfig;
}

export async function loadConfig() {
  if (!configPromise) {
    configPromise = fetch(DEFAULT_CONFIG_PATH, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `Failed to load runtime config from ${DEFAULT_CONFIG_PATH}: ${response.status} ${response.statusText}`,
          );
        }
        return response.json();
      })
      .then(validateRuntimeConfig)
      .then((runtimeConfig) => {
        resolvedConfig = freezeConfig(runtimeConfig);
        return resolvedConfig;
      })
      .catch((error) => {
        resolvedConfig = null;
        configPromise = null;
        throw error;
      });
  }

  return configPromise;
}

export function getConfig() {
  if (!resolvedConfig) {
    throw new Error(
      "Config has not been initialized yet. Call loadConfig() during app bootstrap before importing modules that use config.",
    );
  }
  return resolvedConfig;
}

export function setConfigForTests(config) {
  resolvedConfig = Object.freeze(config);
  configPromise = Promise.resolve(resolvedConfig);
}

export function resetConfigForTests() {
  resolvedConfig = null;
  configPromise = null;
}
