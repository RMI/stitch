function Card({ title, children, className = "" }) {
  return (
    <section
      className={`rounded-md border border-line bg-panel p-4 ${className}`}
    >
      {title && (
        <h2 className="mb-3 text-base font-semibold text-ink">{title}</h2>
      )}
      <div className="text-sm text-ink">{children}</div>
    </section>
  );
}

export default Card;
