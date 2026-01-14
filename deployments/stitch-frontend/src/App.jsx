import ResourcesView from "./components/ResourcesView";

function App() {
  return (
    <div className="min-h-screen w-screen bg-gray-100 p-8">
      <ResourcesView endpoint="/api/v1/resources/" />
    </div>
  );
}

export default App;
