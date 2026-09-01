import { Routes, Route, Link, NavLink } from "react-router";
import EnvironmentBanner from "./components/EnvironmentBanner";
import HomePage from "./pages/HomePage";
import ResourceDetailPage from "./pages/ResourceDetailPage";
import EntityLinkagePage from "./pages/EntityLinkagePage";
import MergeCandidateReviewPage from "./pages/MergeCandidateReviewPage";
import EtlPage from "./pages/EtlPage";
import { LogoutButton } from "./components/LogoutButton";

const NAV_ITEMS = [
  { to: "/", label: "Resources", end: true },
  { to: "/entity-linkage", label: "Entity linkage" },
  { to: "/merge-candidate-review", label: "Merge review" },
  { to: "/etl", label: "ETL pipelines" },
];

function getNavLinkClassName({ isActive }) {
  const base =
    "inline-flex min-h-9 items-center rounded-md px-3 py-2 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bluespruce";

  if (isActive) {
    return `${base} bg-energy text-bluespruce`;
  }

  return `${base} text-calm hover:bg-rmiblue-800 hover:text-neutral-50`;
}

function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <EnvironmentBanner />

      <header className="border-b border-energy/60 bg-bluespruce">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Link
              to="/"
              className="inline-flex min-w-0 items-baseline gap-2 rounded-sm text-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60 focus-visible:ring-offset-4 focus-visible:ring-offset-bluespruce"
            >
              <span className="text-lg font-semibold">Stitch</span>
              <span className="hidden text-sm font-medium text-energy-100 sm:inline">
                Oil and Gas
              </span>
            </Link>

            <LogoutButton />
          </div>

          <nav className="flex flex-wrap gap-1" aria-label="Primary">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={getNavLinkClassName}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/oil-gas-fields/:id" element={<ResourceDetailPage />} />
          <Route path="/entity-linkage" element={<EntityLinkagePage />} />
          <Route
            path="/merge-candidate-review"
            element={<MergeCandidateReviewPage />}
          />
          <Route path="/etl" element={<EtlPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
