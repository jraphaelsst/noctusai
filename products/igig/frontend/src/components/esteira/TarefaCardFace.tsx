/**
 * The face of one esteira card (smoke finding 5: cards showed only a title —
 * no cliente, pauta, responsável or prazo, so a phone user had to open every
 * card to know what it was).
 *
 * Presentation only: the drag handle, activation and snap-back dimming are the
 * seed `KanbanBoard`'s. No buttons here on purpose — actions live in the detail
 * sheet, so a tap is always "open", never a mis-hit on a tiny icon mid-scroll.
 */
import { Badge } from "@noctusai/lib/design-system";
import { CalendarClock, RotateCcw, User } from "lucide-react";

import type { TarefaCard } from "@/hooks/useEsteira";
import { formatarPrazo, prazoVencido } from "./formatos";

export function TarefaCardFace({
  tarefa,
  isDragging,
}: {
  tarefa: TarefaCard;
  isDragging?: boolean;
}) {
  const vencido = prazoVencido(tarefa.prazo);
  return (
    <div
      className={`rounded-md border bg-background p-3 text-left shadow-sm ${
        isDragging ? "border-primary shadow-md" : "border-border"
      }`}
      data-testid="tarefa-card"
    >
      {tarefa.cliente && (
        <p className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {tarefa.cliente.nome}
        </p>
      )}
      <p className="mt-0.5 line-clamp-2 text-sm font-medium text-foreground">{tarefa.titulo}</p>

      {tarefa.pauta && (
        <p className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
          <span className="min-w-0 truncate">{tarefa.pauta.titulo}</span>
          {tarefa.pauta.formato && (
            <Badge variant="outline" className="shrink-0 px-1.5 py-0 text-[10px]">
              {tarefa.pauta.formato}
            </Badge>
          )}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="flex min-w-0 items-center gap-1 text-muted-foreground">
          <User className="h-3 w-3 shrink-0" />
          <span className="truncate">{tarefa.responsavel?.nome ?? "Sem responsável"}</span>
        </span>
        {tarefa.prazo && (
          <span
            className={`flex items-center gap-1 ${
              vencido ? "font-medium text-destructive" : "text-muted-foreground"
            }`}
            title={vencido ? "Prazo vencido" : "Prazo"}
          >
            <CalendarClock className="h-3 w-3 shrink-0" />
            {formatarPrazo(tarefa.prazo)}
            {vencido && <span className="sr-only"> (vencido)</span>}
          </span>
        )}
        {tarefa.refacoes > 0 && (
          <Badge variant="destructive" className="gap-1 px-1.5 py-0 text-[10px]">
            <RotateCcw className="h-3 w-3" />
            {tarefa.refacoes} {tarefa.refacoes === 1 ? "refação" : "refações"}
          </Badge>
        )}
      </div>
    </div>
  );
}
