/** "Possível duplicado" badge — amber; shown when a pendente pair exists. */
import { cn } from "@/lib/utils";

export default function ImovelDuplicadoBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
        "bg-warning-light text-warning-foreground",
        className,
      )}
      data-testid="imovel-duplicado-badge"
    >
      Possível duplicado
    </span>
  );
}
