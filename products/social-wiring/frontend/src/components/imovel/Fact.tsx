/**
 * Fact — one labelled value in a detail-section grid.
 *
 * Extracted from ImovelDetalhes.tsx so every CONTRACT § 5 section component
 * can share it instead of each re-declaring the same icon+label+value shape.
 */
import type { ReactNode } from "react";

export default function Fact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="space-y-1">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {icon}
        {label}
      </p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}
