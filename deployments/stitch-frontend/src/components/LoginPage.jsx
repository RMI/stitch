import { useAuth0 } from "@auth0/auth0-react";
import Button from "./Button";

export default function LoginPage() {
  const { loginWithRedirect } = useAuth0();

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-md rounded-md border border-line bg-panel p-6">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">
          Stitch
        </h1>
        <p className="mt-1 font-mono text-xs text-ink-muted">
          oil-and-gas asset data platform
        </p>
        <p className="mb-6 mt-5 text-sm leading-6 text-ink-muted">
          Integrate diverse datasets, apply AI-driven enrichment with human
          review, and deliver curated, trustworthy data.
        </p>
        <Button onClick={() => loginWithRedirect()}>Log in to continue</Button>
      </div>
    </div>
  );
}
