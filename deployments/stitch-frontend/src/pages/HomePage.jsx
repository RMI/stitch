import ResourcesView from "../components/ResourcesView";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function HomePage() {
  useDocumentTitle("Resources");
  return <ResourcesView endpoint="oil-gas-fields" />;
}
