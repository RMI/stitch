import Card from "./Card";

export default function Jsonview({
  data,
  isLoading,
  isError,
  error,
  message = "No data loaded. Click the button above to fetch data.",
}) {
  if (isError) {
    const errorMessage = error?.status === 404 ? "Not Found" : error.message;
    return (
      <>
        {error?.status === 404 ? (
          <Card title="" className="mb-6 border-2 border-gray-500">
            <p className="text-gray-600">Not Found</p>
          </Card>
        ) : (
          <Card title="Error" className="mb-6 border-2 border-red-500">
            <p className="text-red-600">{errorMessage}</p>
          </Card>
        )}
      </>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <p className="text-gray-500 text-center">Loading...</p>
      </Card>
    );
  }

  if (data) {
    return (
      <Card title="Resources">
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </Card>
    );
  }

  if (!isLoading && !data) {
    return (
      <Card>
        <p className="text-gray-500 text-center">{message}</p>
      </Card>
    );
  }

  return null;
}
