import OGFieldsView from "./components/OGFieldsView";
import OGFieldView from "./components/OGFieldView";
import { LogoutButton } from "./components/LogoutButton";

function App() {
  return (
    <div className="min-h-screen w-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto flex justify-end mb-4">
        <LogoutButton />
      </div>
      <OGFieldsView endpoint="/api/v1/oil-gas-fields" />
      <OGFieldView className="mt-24" endpoint="/api/v1/oil-gas-fields/{id}" />
    </div>
  );
}

export default App;
