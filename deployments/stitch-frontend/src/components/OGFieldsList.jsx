import Card from "./Card";

function OGFieldsList({ ogfields, isLoading, isError, error }) {
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

  if (ogfields?.length > 0) {
    return (
      <Card title="OGField IDs">
        <ul>
          {ogfields.map((ogfield, index) => (
            <span key={ogfield.id}>
              {ogfield.id}
              {index < ogfields.length - 1 ? ", " : ""}
            </span>
          ))}
        </ul>
        <hr className="my-4" />
        <pre>{JSON.stringify(ogfields, null, 2)}</pre>
      </Card>
    );
  }

  if (!isLoading && !ogfields?.length) {
    return (
      <Card>
        <p className="text-gray-500 text-center">
          No ogfields loaded. Click the button above to fetch ogfields.
        </p>
      </Card>
    );
  }

  return null;
}

export default OGFieldsList;
