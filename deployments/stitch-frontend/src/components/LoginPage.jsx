import { useAuth0 } from "@auth0/auth0-react";
import Button from "./Button";

export default function LoginPage() {
  const { loginWithRedirect } = useAuth0();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center max-w-md px-6">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">Stitch</h1>
        <p className="text-lg text-gray-500 mb-6">
          Oil &amp; Gas Asset Data Platform
        </p>
        <p className="text-gray-600 mb-8">
          Integrate diverse datasets, apply AI-driven enrichment with human
          review, and deliver curated, trustworthy data.
        </p>
        <Button onClick={() => loginWithRedirect()}>Log in to continue</Button>
      </div>
    </div>
  );
}
