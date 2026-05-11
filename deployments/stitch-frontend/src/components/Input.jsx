function Input({
  value,
  onChange,
  type = "text",
  className,
  autoSize = false,
  min,
  max,
  ...props
}) {
  const baseStyles =
    "min-h-9 rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink transition-colors hover:border-line-strong focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

  const handleClick = (e) => {
    e.target.select();
  };

  // Dynamically set the size of the input based on the value
  const inputSize =
    autoSize && value ? Math.max(String(value).length, 1) : undefined;

  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      onClick={handleClick}
      className={`${baseStyles} ${className || ""}`}
      size={inputSize}
      min={min}
      max={max}
      {...props}
    />
  );
}

export default Input;
