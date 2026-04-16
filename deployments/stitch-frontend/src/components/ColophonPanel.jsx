import { useEffect, useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import config from "../config/env";
import useBackendDiagnostics from "../hooks/useBackendDiagnostics";

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

function formatBackendSection(state) {
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

  const data = state.data;
  const runtime = data.runtime ?? {};
  const auth = data.auth ?? {};
  const frontend = data.frontend ?? {};
  const database = data.database ?? {};
  const build = data.build ?? {};

  return {
    Status: data.status ?? "unknown",
    Service: data.service ?? "unknown",
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
  const systemInfo = useSystemInfo();
  const backendDiagnostics = useBackendDiagnostics(diagnosticsOpen);
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuth0();

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
        const token = await getAccessTokenSilently();

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
  }, [getAccessTokenSilently, isAuthenticated, isLoading]);

  const sections = useMemo(() => {
    return {
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
      "Backend Diagnostics": formatBackendSection(backendDiagnostics),
      "Runtime Info": {
        "User Agent": systemInfo.userAgent,
        "Screen Resolution": systemInfo.screenResolution,
        "Device Pixel Ratio": systemInfo.devicePixelRatio,
        Language: systemInfo.language,
        Connection: systemInfo.connectionType,
      },
    };
  }, [systemInfo, backendDiagnostics, accessToken, tokenStatus]);

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
    <div className="border-b border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-4xl px-4 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">Diagnostics</h2>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleCopyToken()}
              disabled={!accessToken}
              className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
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
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-100"
                title="Open FastAPI docs"
              >
                API docs
              </a>
            ) : (
              <span
                className="rounded border border-red-300 bg-red-50 px-3 py-1.5 text-sm text-red-700"
                title="API docs URL unavailable for current API base URL"
              >
                API docs unavailable
              </span>
            )}

            <button
              type="button"
              onClick={() => void handleCopy()}
              className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-100"
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
              className="rounded border border-slate-200 bg-white p-4"
            >
              <h3 className="mb-2 text-sm font-semibold text-slate-900">
                {section}
              </h3>

              <dl className="space-y-2 text-sm">
                {Object.entries(values).map(([key, value]) => (
                  <div key={key} className="grid grid-cols-[140px_1fr] gap-3">
                    <dt className="font-medium text-slate-700">{key}</dt>
                    <dd className="break-all text-slate-900">{value}</dd>
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
