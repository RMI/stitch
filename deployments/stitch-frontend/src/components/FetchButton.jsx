import Button from "./Button";

function FetchButton({ onFetch, isLoading }) {
  return (
    <Button onClick={onFetch} disabled={isLoading} variant="primary">
      {isLoading ? "Loading..." : "Fetch"}
    </Button>
  );
}

export default FetchButton;
