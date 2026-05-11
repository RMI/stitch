import { useMemo, useState } from "react";
import Card from "./Card";
import ResourcesTable from "./ResourcesTable";
import { getResourceField } from "../utils/resourceDisplay";

function sortResources(resources, sortConfig) {
  if (!sortConfig.column) return resources;

  const direction = sortConfig.direction === "desc" ? -1 : 1;

  return [...resources].sort((a, b) => {
    const aValue = getResourceField(a, sortConfig.column);
    const bValue = getResourceField(b, sortConfig.column);

    if (aValue == null && bValue == null) return 0;
    if (aValue == null) return 1;
    if (bValue == null) return -1;

    return String(aValue).localeCompare(String(bValue)) * direction;
  });
}

function ResourcesList({ resources, isLoading, isError, error }) {
  const [sortConfig, setSortConfig] = useState({
    column: null,
    direction: "asc",
  });
  const sortedResources = useMemo(
    () => sortResources(resources ?? [], sortConfig),
    [resources, sortConfig],
  );

  if (isError) {
    return (
      <Card title="Error" className="mb-6 border-danger/25 bg-danger-soft">
        <p className="text-danger">{error.message}</p>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <p className="text-center text-ink-muted">Loading...</p>
      </Card>
    );
  }

  if (resources?.length > 0) {
    return (
      <Card title="Resources">
        <ResourcesTable
          resources={sortedResources}
          sortConfig={sortConfig}
          onSort={setSortConfig}
        />
      </Card>
    );
  }

  if (!isLoading && !resources?.length) {
    return (
      <Card>
        <p className="text-center text-ink-muted">
          No resources loaded. Click the button above to fetch resources.
        </p>
      </Card>
    );
  }

  return null;
}

export default ResourcesList;
