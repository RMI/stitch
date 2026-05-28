import { useEffect, useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { createAuthenticatedFetcher } from "../auth/api";
import useBackendDiagnostics from "../hooks/useBackendDiagnostics";
import { useConfig } from "../config/useConfig";

function getConnectionInfo() {
  const nav = navigator;

  if (!("connection" in nav)) {
    return "Not available";
  }

  const connection = nav.connection;
  const effectiveType = connection?.effectiveType ?? "unknown";
  const downlink = connection?.downlink;

  if (typeof downlink === "number") {
    return `${effectiveType} (${downlink} Mbps)`;
  }

  return effectiveType;
}

function useSystemInfo() {
  return useMemo(
    () => ({
      userAgent: navigator.userAgent,
      screenResolution: `${window.innerWidth}x${window.innerHeight}`,
      connectionType: getConnectionInfo(),
      language: navigator.language || "N/A",
      devicePixelRatio: `${window.devicePixelRatio}x`,
    }),
    [],
  );
}

function formatBackendSection(config, state) {
  if (state.loading) {
    return {
      Status: "Loading...",
    };
  }

  if (state.error) {
    return {
      Status: "Unavailable",
      Error: state.error,
      Endpoint: `${config.apiBaseUrl}/health/details`,
    };
  }

  if (!state.data || typeof state.data !== "object") {
    return {
      Status: "Unavailable",
      Endpoint: `${config.apiBaseUrl}/health/details`,
    };
  }

  const health = state.data.health ?? {};
  const authMe = state.data.authMe ?? {};
  const runtime = health.runtime ?? {};
  const auth = health.auth ?? {};
  const frontend = health.frontend ?? {};
  const database = health.database ?? {};
  const build = health.build ?? {};
  const claims = authMe.claims ?? {};
  const authUser = authMe.user ?? {};
  const permissions = Array.isArray(claims.permissions)
    ? claims.permissions
    : [];

  const section = {
    Status: health.status ?? "unknown",
    Service: health.service ?? "unknown",
    Environment: runtime.environment ?? "unknown",
    "Started At": runtime.started_at ?? "unknown",
    "Uptime (s)": String(runtime.uptime_seconds ?? "unknown"),
    "Auth Disabled": String(auth.disabled ?? "unknown"),
    "Auth Validated": String(auth.startup_validated ?? "unknown"),
    "Frontend Origin": frontend.origin ?? "unknown",
    "DB Dialect": database.dialect ?? "unknown",
    "DB Host": database.host ?? "n/a",
    "DB Port": String(database.port ?? "n/a"),
    "DB Name": database.database ?? "unknown",
    "DB Reachable": String(database.reachable ?? "unknown"),
    "Build Version": build.app_version ?? "unknown",
    "Build ID": build.build_id ?? "unknown",
    "Build Git SHA": build.git_sha
      ? String(build.git_sha).slice(0, 7)
      : "unknown",
    "Build Time": build.build_time ?? "unknown",
  };

  if (state.data.authMeError) {
    return {
      ...section,
      "Auth Claims Status": "Unavailable",
      "Auth Claims Error": state.data.authMeError,
    };
  }

  if (!state.authClaimsRequested) {
    return {
      ...section,
      "Auth Claims Status": "Not requested",
    };
  }

  return {
    ...section,
    "Auth Claims Status": "Available",
    "Auth Subject": claims.sub ?? "unknown",
    "Auth User ID": authUser.id != null ? String(authUser.id) : "unknown",
    "Auth Email": claims.email ?? authUser.email ?? "unknown",
    "Auth Name": claims.name ?? authUser.name ?? "unknown",
    "Auth Permissions":
      permissions.length > 0 ? permissions.join(", ") : "none",
  };
}

function redactToken(token) {
  if (!token) {
    return "Unavailable";
  }

  if (token.length <= 24) {
    return token;
  }

  return `${token.slice(0, 12)}...${token.slice(-8)}`;
}

function getApiDocsUrl(apiBaseUrl) {
  if (!apiBaseUrl) {
    return null;
  }

  const match = apiBaseUrl.match(/^(.*)\/api\/v1\/?$/);
  if (!match) {
    return null;
  }

  return `${match[1]}/docs`;
}

export default function ColophonPanel({ diagnosticsOpen = false }) {
  const config = useConfig();
  const systemInfo = useSystemInfo();
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuth0();
  const authenticatedFetcher = useMemo(() => {
    if (!isAuthenticated) {
      return null;
    }
    return createAuthenticatedFetcher(config, getAccessTokenSilently);
  }, [config, getAccessTokenSilently, isAuthenticated]);
  const backendDiagnostics = useBackendDiagnostics(
    config.apiBaseUrl,
    diagnosticsOpen,
    authenticatedFetcher,
  );
  const backendDiagnosticsWithAuth = useMemo(
    () => ({
      ...backendDiagnostics,
      authClaimsRequested: isAuthenticated,
    }),
    [backendDiagnostics, isAuthenticated],
  );

  const [accessToken, setAccessToken] = useState("");
  const [tokenStatus, setTokenStatus] = useState("Loading...");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [tokenCopyError, setTokenCopyError] = useState(false);

  const apiDocsUrl = getApiDocsUrl(config.apiBaseUrl);

  useEffect(() => {
    let cancelled = false;

    async function loadToken() {
      if (isLoading) {
        return;
      }

      if (!isAuthenticated) {
        setTokenStatus("Not authenticated");
        setAccessToken("");
        return;
      }

      try {
        const token = await getAccessTokenSilently({
          authorizationParams: { audience: config.auth0.audience },
        });

        if (!cancelled) {
          setAccessToken(token);
          setTokenStatus("Available");
        }
      } catch (error) {
        console.error("Failed to load access token:", error);

        if (!cancelled) {
          setAccessToken("");
          setTokenStatus("Unavailable");
        }
      }
    }

    void loadToken();

    return () => {
      cancelled = true;
    };
  }, [
    config.auth0.audience,
    getAccessTokenSilently,
    isAuthenticated,
    isLoading,
  ]);

  const sections = {
    "Frontend Build Info": {
      Environment: config.appEnv,
      "API Base URL": config.apiBaseUrl,
      "App Version": config.build.appVersion,
      "Build ID": config.build.buildId,
      "Git SHA": config.build.gitSha.slice(0, 7),
      "Node Version": config.build.nodeVersion,
      "Vite Version": config.build.viteVersion,
      "Build Time": config.build.buildTime,
      "Bearer Token": accessToken ? redactToken(accessToken) : tokenStatus,
    },
    "Backend Diagnostics": formatBackendSection(
      config,
      backendDiagnosticsWithAuth,
    ),
    "Runtime Info": {
      "User Agent": systemInfo.userAgent,
      "Screen Resolution": systemInfo.screenResolution,
      "Device Pixel Ratio": systemInfo.devicePixelRatio,
      Language: systemInfo.language,
      Connection: systemInfo.connectionType,
    },
  };

  async function handleCopy() {
    const safeSections = {
      ...sections,
      "Frontend Build Info": {
        ...sections["Frontend Build Info"],
        "Bearer Token": accessToken
          ? "[redacted - use Copy token]"
          : tokenStatus,
      },
    };

    const text = Object.entries(safeSections)
      .map(([section, values]) => {
        const body = Object.entries(values)
          .map(([key, value]) => `${key}: ${value}`)
          .join("\n");

        return `### ${section} ###\n${body}`;
      })
      .join("\n\n");

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setCopyError(false);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy diagnostics:", error);
      setCopyError(true);
      setCopied(false);
      window.setTimeout(() => setCopyError(false), 2000);
    }
  }

  async function handleCopyToken() {
    if (!accessToken) {
      return;
    }

    try {
      await navigator.clipboard.writeText(`Bearer ${accessToken}`);
      setTokenCopied(true);
      setTokenCopyError(false);
      window.setTimeout(() => setTokenCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy token:", error);
      setTokenCopyError(true);
      setTokenCopied(false);
      window.setTimeout(() => setTokenCopyError(false), 2000);
    }
  }

  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:px-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">Diagnostics</h2>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => void handleCopyToken()}
              disabled={!accessToken}
              className="rounded-md border border-line bg-panel px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              title="Copy Bearer token for API tools"
            >
              {tokenCopied
                ? "Token copied!"
                : tokenCopyError
                  ? "Token copy failed"
                  : "Copy token"}
            </button>

            {apiDocsUrl ? (
              <a
                href={apiDocsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md border border-line bg-panel px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2"
                title="Open FastAPI docs"
              >
                API docs
              </a>
            ) : (
              <span
                className="rounded-md border border-danger/25 bg-danger-soft px-3 py-1.5 text-sm font-medium text-danger"
                title="API docs URL unavailable for current API base URL"
              >
                API docs unavailable
              </span>
            )}

            <button
              type="button"
              onClick={() => void handleCopy()}
              className="rounded-md border border-line bg-panel px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2"
              title="Copy diagnostic information"
            >
              {copied ? "Copied!" : copyError ? "Copy failed" : "Copy"}
            </button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(sections).map(([section, values]) => (
            <div
              key={section}
              className="rounded-md border border-line bg-panel p-4"
            >
              <h3 className="mb-2 text-sm font-semibold text-ink">{section}</h3>

              <dl className="space-y-2 text-sm">
                {Object.entries(values).map(([key, value]) => (
                  <div
                    key={key}
                    className="grid gap-1 sm:grid-cols-[140px_1fr] sm:gap-3"
                  >
                    <dt className="font-medium text-ink-muted">{key}</dt>
                    <dd className="break-all text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
