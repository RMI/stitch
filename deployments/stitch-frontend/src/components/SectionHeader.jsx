export default function SectionHeader({ title }) {
  return (
    <div className="mb-4">
      <h2 className="text-2xl font-semibold text-gray-dark text-left">
        {title}
      </h2>
      <hr className="mt-1 border-gray-dark" />
    </div>
  );
}
