/** Empty state component shown when no data exists. */

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 text-4xl opacity-20">◇</div>
      <h3 className="text-lg font-medium text-gray-400">{title}</h3>
      <p className="mt-1 text-sm text-gray-500">{description}</p>
    </div>
  );
}
