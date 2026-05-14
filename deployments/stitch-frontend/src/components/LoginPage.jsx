import { useAuth0 } from "@auth0/auth0-react";
import Button from "./Button";

export default function LoginPage() {
  const { loginWithRedirect } = useAuth0();

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-md rounded-md border border-line bg-panel p-6">
        <h1 className="text-3xl font-semibold text-ink">Stitch</h1>
        <p className="mt-2 text-base font-medium text-ink-muted">
          Oil &amp; Gas Asset Data Platform
        </p>
        <p className="mb-6 mt-4 text-sm leading-6 text-ink-muted">
          Integrate diverse datasets, apply AI-driven enrichment with human
          review, and deliver curated, trustworthy data.
        </p>
        <Button onClick={() => loginWithRedirect()}>Log in to continue</Button>
      </div>
    </div>
  );
}
