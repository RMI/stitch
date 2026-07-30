export const SOURCES = ["rmi", "wm", "ccr", "gem", "llm"];

/**
 * Priority order for coalescing a value across sources, best first. Mirrors
 * the backend's canonical SOURCE_PRIORITY in
 * packages/stitch-ogsi/src/stitch/ogsi/model, which is the single source of
 * truth. Keep this list in sync with it until the constant is generated.
 */
export const SOURCE_PRIORITY = ["rmi", "wm", "ccr", "gem", "llm"];

export const SOURCE_COLORS = {
  gem: "#45cfcc", // energy teal
  wm: "#7b76ad", // RMI purple
  ccr: "#f2994a", // amber
  rmi: "#ffcb00", // solar
  llm: "#529cba", // RMI blue
};

export const SOURCE_LABELS = {
  llm: "LLM",
  gem: "GEM Database",
  wm: "Woodmac Database",
  ccr: "C&C Reservoirs",
  rmi: "User Generated",
};

export const UNKNOWN_SOURCE_LABEL = "Source unavailable";

/** Neutral border color when no source is specified or recognized. */
export const DEFAULT_FIELD_COLOR = "#d6dde2";
