export const SOURCES = ["gem", "wm", "rmi", "llm"];

export const SOURCE_COLORS = {
  gem: "#4AE3D9", // teal
  wm: "#3B44EC", // purple
  rmi: "#F4A70B", // orange
  llm: "#57A0FF", // light blue
};

export const SOURCE_LABELS = {
  llm: "LLM",
  gem: "GEM Database",
  wm: "Woodmac Database",
  rmi: "User Generated",
};

/** Default border color when no source is specified (Tailwind blue-300). */
// export const DEFAULT_FIELD_COLOR = "#93c5fd";
export const DEFAULT_FIELD_COLOR = SOURCE_COLORS.gem;
