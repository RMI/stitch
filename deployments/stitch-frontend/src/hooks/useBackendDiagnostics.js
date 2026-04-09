import { useEffect, useState } from "react";
import config from "../config/env";

export default function useBackendDiagnostics(enabled) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    data: null,
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let cancelled = false;

    async function load() {
      setState((current) => ({
        ...current,
        loading: true,
        error: null,
      }));

      try {
        const response = await fetch(`${config.apiBaseUrl}/health/details`, {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        });

        const payload = await response.json().catch(() => null);

        if (!response.ok) {
          const detail =
            payload && typeof payload === "object" && "detail" in payload
              ? payload.detail
              : `HTTP ${response.status}`;

          throw new Error(
            typeof detail === "string" ? detail : JSON.stringify(detail),
          );
        }

        if (!cancelled) {
          setState({
            loading: false,
            error: null,
            data: payload,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            loading: false,
            error: error instanceof Error ? error.message : "Unknown error",
            data: null,
          });
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return state;
}
