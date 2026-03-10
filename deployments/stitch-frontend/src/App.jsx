import OGFieldsView from "./components/OGFieldsView";
import OGFieldView from "./components/OGFieldView";
import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ResourceDetailPage from "./pages/ResourceDetailPage";
import { LogoutButton } from "./components/LogoutButton";

function App() {
  return (
    <div className="min-h-screen w-screen bg-white p-8">
      <div className="max-w-4xl mx-auto flex justify-end mb-4">
        <LogoutButton />
      </div>
      <OGFieldsView endpoint="/api/v1/oil-gas-fields" />
      <OGFieldView className="mt-24" endpoint="/api/v1/oil-gas-fields/{id}" />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/resources/:id" element={<ResourceDetailPage />} />
      </Routes>
    </div>
  );
}

export default App;
