function Card({ title, children, className = "" }) {
  return (
    <div className={`bg-white rounded-lg shadow-lg p-6 ${className}`}>
      {title && (
        <h2 className="text-xl font-bold mb-4 text-gray-800">{title}</h2>
      )}
      <div className="text-gray-700">{children}</div>
    </div>
  );
}

export default Card;
