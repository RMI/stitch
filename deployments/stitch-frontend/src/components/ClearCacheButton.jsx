import Button from "./Button";

function ClearCacheButton({ onClear, disabled }) {
  return (
    <Button onClick={onClear} variant="secondary" disabled={disabled}>
      Clear Cache
    </Button>
  );
}

export default ClearCacheButton;
