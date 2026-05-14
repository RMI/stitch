import Card from "./Card";
import StructuredDataView from "./StructuredDataView";

export default function JsonView({
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
          <Card title="" className="mb-6 border-line-strong bg-surface">
            <p className="font-medium text-ink-muted">Not Found</p>
          </Card>
        ) : (
          <Card title="Error" className="mb-6 border-danger/25 bg-danger-soft">
            <p className="text-danger">{errorMessage}</p>
          </Card>
        )}
      </>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <p className="text-center text-ink-muted">Loading...</p>
      </Card>
    );
  }

  if (data) {
    return (
      <Card title="Resource data">
        <StructuredDataView data={data} label="Resource data" />
      </Card>
    );
  }

  if (!isLoading && !data) {
    return (
      <Card>
        <p className="text-center text-ink-muted">{message}</p>
      </Card>
    );
  }

  return null;
}
