/** "Possível duplicado" badge — amber; shown when a pendente pair exists. */
import { cn } from "@/lib/utils";

export default function ImovelDuplicadoBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
        "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        className,
      )}
      data-testid="imovel-duplicado-badge"
    >
      Possível duplicado
    </span>
  );
}
