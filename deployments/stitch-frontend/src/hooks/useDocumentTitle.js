import { useEffect } from "react";

// Sets the browser tab title. Callers pass the page-specific portion
// (e.g. "Resources"); the app name suffix is applied here so the format
// stays consistent across routes.
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} - Stitch` : "Stitch";
  }, [title]);
}
