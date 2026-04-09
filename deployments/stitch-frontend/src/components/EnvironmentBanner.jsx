import { useState } from "react";
import config from "../config/env";
import ColophonPanel from "./ColophonPanel";

function normalizeEnvLabel(value) {
  return (value ?? "").trim();
}

function isProductionEnv(label) {
  const normalized = label.toLowerCase();
  return normalized === "production" || normalized === "prod";
}

function getBannerClasses(label) {
  const normalized = label.toLowerCase();

  if (normalized === "main") {
    return "bg-green-500 text-white";
  } else if (normalized === "next") {
    return "bg-yellow-500 text-white";
  } else if (normalized.startsWith("hotfix")) {
    return "bg-orange-500 text-white";
  } else if (normalized.startsWith("develop")) {
    return "bg-red-500 text-white";
  } else if (normalized.startsWith("pr-")) {
    return "bg-indigo-500 text-white";
  } else {
    return "bg-pink-500 text-white";
  }
}

export default function EnvironmentBanner() {
  const [isOpen, setIsOpen] = useState(false);
  const label = normalizeEnvLabel(config.appEnv);

  if (!label || isProductionEnv(label)) {
    return null;
  }

  return (
    <div className="sticky top-0 z-50 w-full">
      <div className={getBannerClasses(label)}>
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-1 text-sm font-medium">
          <span>{label.toUpperCase()} Environment</span>

          <button
            type="button"
            onClick={() => setIsOpen((value) => !value)}
            className="rounded border border-white/30 px-2 py-0.5 text-sm hover:bg-white/10"
            aria-expanded={isOpen}
            aria-controls="frontend-diagnostics-panel"
          >
            {isOpen ? "Hide diagnostics" : "Show diagnostics"}
          </button>
        </div>
      </div>

      {isOpen ? (
        <div id="frontend-diagnostics-panel">
          <ColophonPanel diagnosticsOpen={isOpen} />
        </div>
      ) : null}
    </div>
  );
}
