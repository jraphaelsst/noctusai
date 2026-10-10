/**
 * "Manual" badge — marks an imóvel registered on the platform (`fonte:
 * "manual"`, or a hand-registered registry código, `origem: "manual"`) so an
 * agent can tell it from a Vista listing at a glance. Small, neutral sky tone.
 */
import { cn } from "@/lib/utils";

/** True for a manual imóvel from any of the shapes that carry the fact. */
export function ehImovelManual(i: {
  fonte?: string | null;
  origem?: string | null;
}): boolean {
  return i.fonte === "manual" || i.origem === "manual";
}

export default function ImovelManualBadge({
  label = "Manual",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
        "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
        className,
      )}
      data-testid="imovel-manual-badge"
    >
      {label}
    </span>
  );
}
