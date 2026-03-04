import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ResourceDetailPage from "./pages/ResourceDetailPage";
import { LogoutButton } from "./components/LogoutButton";

function App() {
  return (
    <div className="min-h-screen w-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto flex justify-end mb-4">
        <LogoutButton />
      </div>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/resources/:id" element={<ResourceDetailPage />} />
      </Routes>
    </div>
  );
}

export default App;
