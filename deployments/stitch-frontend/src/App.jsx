import { Routes, Route, Link, NavLink } from "react-router";
import EnvironmentBanner from "./components/EnvironmentBanner";
import HomePage from "./pages/HomePage";
import ResourceDetailPage from "./pages/ResourceDetailPage";
import EntityLinkagePage from "./pages/EntityLinkagePage";
import MergeCandidateReviewPage from "./pages/MergeCandidateReviewPage";
import EtlPage from "./pages/EtlPage";
import { LogoutButton } from "./components/LogoutButton";
import { usePermissions } from "./hooks/usePermissions";

// Mirrors SOURCE_READ_PERMISSIONS in packages/stitch-auth. ETL runs produce or
// refresh source data, so the page is useful to anyone who can read or write at
// least one source.
const SOURCE_READ_PERMISSIONS = [
  "source:read:rmi",
  "source:read:gem",
  "source:read:wm",
  "source:read:llm",
  "source:read:ccr",
  "source:read:bc",
  "source:read:alb",
];

// `requires` is a has-any list: an item is visible if the caller holds any of
// the listed permissions. Items without `requires` are ungated.
const NAV_ITEMS = [
  { to: "/", label: "Resources", end: true },
  {
    to: "/entity-linkage",
    label: "Entity linkage",
    requires: ["service:entity-linkage:run"],
  },
  {
    to: "/merge-candidate-review",
    label: "Merge review",
    requires: ["merge-candidate:read"],
  },
  {
    to: "/etl",
    label: "ETL pipelines",
    requires: [...SOURCE_READ_PERMISSIONS, "source:write"],
  },
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
  // Cached /auth/me permissions gate the nav items below. While loading we hide
  // gated items rather than flashing them in once claims resolve, matching the
  // pattern used on ResourceDetailPage.
  const { data: permissions, isLoading: permissionsLoading } = usePermissions();
  const granted = Array.isArray(permissions) ? permissions : [];
  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (!item.requires) return true;
    if (permissionsLoading) return false;
    return item.requires.some((permission) => granted.includes(permission));
  });

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
            {visibleNavItems.map((item) => (
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
