export default function SectionHeader({ title }) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-semibold text-gray-700 text-left">{title}</h2>
      <hr className="mt-1 border-gray-300" />
    </div>
  );
}
