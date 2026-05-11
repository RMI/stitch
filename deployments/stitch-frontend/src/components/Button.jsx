function Button({
  children,
  onClick,
  variant = "primary",
  className = "",
  type = "button",
  ...props
}) {
  const baseStyles =
    "inline-flex min-h-9 items-center justify-center rounded-md border px-3 py-2 text-sm font-semibold leading-5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-55";

  const variants = {
    primary:
      "border-bluespruce bg-bluespruce text-neutral-50 hover:bg-rmiblue-800",
    secondary:
      "border-neutral-300 bg-panel text-bluespruce hover:border-slate hover:bg-rmiblue-100",
    ghost:
      "border-transparent bg-transparent text-neutral-700 hover:bg-rmiblue-100 hover:text-bluespruce",
    danger:
      "border-error-600 bg-error-600 text-neutral-50 hover:border-error-800 hover:bg-error-800",
    confirm:
      "border-success-600 bg-success-600 text-neutral-900 hover:border-success-800 hover:bg-success-800 hover:text-neutral-50",
  };

  return (
    <button
      type={type}
      className={`${baseStyles} ${variants[variant] ?? variants.primary} ${className}`}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
}

export default Button;
