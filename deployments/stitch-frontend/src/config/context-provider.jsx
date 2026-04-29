import { ConfigContext } from "./context";

export function ConfigProvider({ config, children }) {
  if (!config || typeof config !== "object") {
    throw new Error("ConfigProvider requires a valid config object.");
  }

  return (
    <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>
  );
}
