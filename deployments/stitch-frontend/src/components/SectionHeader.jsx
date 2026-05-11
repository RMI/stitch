export default function SectionHeader({ title }) {
  return (
    <div className="mb-3 border-b border-energy-400 pb-2">
      <h2 className="text-left text-lg font-semibold text-bluespruce">
        {title}
      </h2>
    </div>
  );
}
