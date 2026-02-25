import ResourcesView from "./components/ResourcesView";
import ResourceView from "./components/ResourceView";
import { LogoutButton } from "./components/LogoutButton";

function App() {
  return (
    <div className="min-h-screen w-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto flex justify-end mb-4">
        <LogoutButton />
      </div>
      <ResourcesView endpoint="/api/v1/resources" />
      <ResourceView className="mt-24" endpoint="/api/v1/resources/{id}" />
    </div>
  );
}

export default App;
