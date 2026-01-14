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
    "px-6 py-3 rounded-lg font-semibold transition-colors duration-200 focus:outline-none focus:ring-1 focus:ring-offset-2 focus:ring-blue-500 border-2 border-gray-300 hover:border-gray-400 focus:border-blue-500";

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
