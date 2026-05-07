import { useEffect, useState } from "react";

async function parseJsonResponse(response) {
  return response.json().catch(() => null);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : `HTTP ${response.status}`;

    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }

  return payload;
}

export default function useBackendDiagnostics(apiBaseUrl, enabled, authFetcher) {
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
        const health = await fetchJson(`${apiBaseUrl}/health/details`, {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        });

        let authMe = null;
        let authMeError = null;

        if (authFetcher) {
          try {
            const response = await authFetcher(`${apiBaseUrl}/auth/me`, {
              method: "GET",
              headers: {
                Accept: "application/json",
              },
            });
            authMe = await parseJsonResponse(response);

            if (!response.ok) {
              const detail =
                authMe && typeof authMe === "object" && "detail" in authMe
                  ? authMe.detail
                  : `HTTP ${response.status}`;
              throw new Error(
                typeof detail === "string" ? detail : JSON.stringify(detail),
              );
            }
          } catch (error) {
            authMeError =
              error instanceof Error ? error.message : "Unknown error";
          }
        }

        if (!cancelled) {
          setState({
            loading: false,
            error: null,
            data: {
              health,
              authMe,
              authMeError,
            },
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
  }, [apiBaseUrl, authFetcher, enabled]);

  return state;
}
