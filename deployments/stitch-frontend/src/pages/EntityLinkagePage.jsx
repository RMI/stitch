import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useConfig } from "../config/useConfig";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";

export default function EntityLinkagePage() {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();

  const [applyMerges, setApplyMerges] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleStart() {
    setLoading(true);
    setError(null);
    setResult(null);

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
        setError({
          status: response.status,
          body: parsed,
        });
        return;
      }

      setResult(parsed);
    } catch (err) {
      setError({
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch workflow
        </p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">Entity Linkage</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Start an entity-linkage run and review the result.
        </p>
      </div>

      <div className="mb-6 rounded-md border border-line bg-panel p-4">
        <label className="flex items-center gap-3 text-sm font-medium text-ink">
          <input
            type="checkbox"
            checked={applyMerges}
            onChange={(e) => setApplyMerges(e.target.checked)}
            className="accent-primary"
          />
          <span>Initiate merges</span>
        </label>

        <div className="mt-4">
          <Button onClick={handleStart} disabled={loading} variant="primary">
            {loading ? "Running…" : "Start run"}
          </Button>
        </div>
      </div>

      {error ? (
        <section className="mb-6">
          <h2 className="mb-2 text-lg font-semibold text-ink">Run error</h2>
          <div className="rounded-md border border-danger/25 bg-danger-soft p-4 text-sm text-danger">
            <StructuredDataView data={error} label="Entity linkage error" />
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="mb-2 text-lg font-semibold text-ink">Run result</h2>
        <div className="rounded-md border border-line bg-panel p-4">
          <StructuredDataView
            data={result}
            label="Entity linkage result"
            emptyMessage="No run has completed yet."
          />
        </div>
      </section>
    </div>
  );
}
