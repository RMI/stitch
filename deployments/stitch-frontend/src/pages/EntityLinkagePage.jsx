import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import config from "../config/env";

export default function EntityLinkagePage() {
  const { getAccessTokenSilently } = useAuth0();

  const [applyMerges, setApplyMerges] = useState(false);
  const [loading, setLoading] = useState(false);
  const [responseJson, setResponseJson] = useState(null);
  const [error, setError] = useState(null);

  async function handleStart() {
    setLoading(true);
    setError(null);

    try {
      const token = await getAccessTokenSilently();

      const response = await fetch(`${config.entityLinkageBaseUrl}/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          apply_merges: applyMerges,
        }),
      });

      const text = await response.text();

      let parsed;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        parsed = { raw: text };
      }

      if (!response.ok) {
        throw new Error(
          JSON.stringify(
            {
              status: response.status,
              body: parsed,
            },
            null,
            2,
          ),
        );
      }

      setResponseJson(parsed);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResponseJson(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Entity Linkage</h1>
        <p className="mt-2 text-sm text-gray-600">
          Start an entity-linkage run and inspect the raw JSON response.
        </p>
      </div>

      <div className="mb-6 rounded border p-4">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={applyMerges}
            onChange={(e) => setApplyMerges(e.target.checked)}
          />
          <span>Initiate merges</span>
        </label>

        <div className="mt-4">
          <button
            type="button"
            onClick={handleStart}
            disabled={loading}
            className="rounded border px-4 py-2 disabled:opacity-50"
          >
            {loading ? "Running..." : "Start"}
          </button>
        </div>
      </div>

      {error ? (
        <section className="mb-6">
          <h2 className="mb-2 text-lg font-medium">Error</h2>
          <pre className="overflow-x-auto rounded border bg-red-50 p-4 text-sm whitespace-pre-wrap">
            {error}
          </pre>
        </section>
      ) : null}

      <section>
        <h2 className="mb-2 text-lg font-medium">Response JSON</h2>
        <pre className="overflow-x-auto rounded border bg-gray-50 p-4 text-sm">
          {JSON.stringify(responseJson, null, 2)}
        </pre>
      </section>
    </main>
  );
}
