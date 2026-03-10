import ResourcesView from "../components/ResourcesView";
import ResourceView from "../components/ResourceView";

export default function HomePage() {
  return (
    <>
      <ResourcesView endpoint="/api/v1/resources" />
      <ResourceView className="mt-24" endpoint="/api/v1/resources/{id}" />
    </>
  );
}
