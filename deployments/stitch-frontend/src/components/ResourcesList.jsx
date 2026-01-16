import Card from "./Card";

function ResourcesList({ resources, isLoading, isError, error }) {
  if (isError) {
    return (
      <Card title="Error" className="mb-6 border-2 border-red-500">
        <p className="text-red-600">{error.message}</p>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <p className="text-gray-500 text-center">Loading...</p>
      </Card>
    );
  }

  if (resources?.length > 0) {
    return (
      <Card title="Resource IDs">
        <ul>
          {resources.map((resource, index) => (
            <span key={resource.id}>
              {resource.id}
              {index < resources.length - 1 ? ", " : ""}
            </span>
          ))}
        </ul>
      </Card>
    );
  }

  if (!isLoading && !resources?.length) {
    return (
      <Card>
        <p className="text-gray-500 text-center">
          No resources loaded. Click the button above to fetch resources.
        </p>
      </Card>
    );
  }

  return null;
}

export default ResourcesList;
