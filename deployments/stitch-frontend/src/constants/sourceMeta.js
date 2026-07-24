export const SOURCES = ["rmi", "wm", "ccr", "gem", "llm"];

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
