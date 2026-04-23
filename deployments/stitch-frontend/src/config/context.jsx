/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from "react";

const ConfigContext = createContext(null);

export function ConfigProvider({ config, children }) {
  if (!config || typeof config !== "object") {
    throw new Error("ConfigProvider requires a valid config object.");
  }

  return (
    <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>
  );
}

export function useConfig() {
  const config = useContext(ConfigContext);

  if (!config) {
    throw new Error("useConfig() must be used within a ConfigProvider.");
  }

  return config;
}
