import { Routes, Route, Link } from "react-router-dom";
import EnvironmentBanner from "./components/EnvironmentBanner";
import HomePage from "./pages/HomePage";
import ResourceDetailPage from "./pages/ResourceDetailPage";
import EntityLinkagePage from "./pages/EntityLinkagePage";
import { LogoutButton } from "./components/LogoutButton";

function App() {
  return (
    <div className="min-h-screen w-screen bg-white">
      <EnvironmentBanner />
      <div className="p-8">
        <nav className="flex gap-4 mb-4" aria-label="Primary">
          <Link to="/">Home</Link>
          <Link to="/entity-linkage">Entity Linkage</Link>
        </nav>
        <div className="max-w-4xl mx-auto flex justify-end mb-4">
          <LogoutButton />
        </div>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/oil-gas-fields/:id" element={<ResourceDetailPage />} />
          <Route path="/entity-linkage" element={<EntityLinkagePage />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
