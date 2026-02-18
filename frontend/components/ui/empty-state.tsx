/**
 * Centered empty state with icon, title, and description.
 * Used when a page section has no data to display.
 */

import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export default function EmptyState({
  icon: Icon,
  title,
  description,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <Icon size={48} className="text-boz-neutral mb-4" />
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-boz-neutral max-w-sm">{description}</p>
    </div>
  );
}
