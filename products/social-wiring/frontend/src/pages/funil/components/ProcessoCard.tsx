/**
 * A Processos de Venda card — one accepted deal in delivery.
 *
 * Clicking the card opens the SAME `LeadDetailModal` the Funil board and
 * the Leads table open, reached through the negociação this processo came
 * from (`PROCESSO_SELECT` carries the origin joins for exactly that).
 *
 * ARCHIVING MOVED INTO THE MODAL
 * ------------------------------
 * The archive/restore control used to sit on the card face. It now lives in
 * the modal footer: an irreversible-looking action one stray click away, on
 * an element that is also a drag handle and now also opens a detail view, is
 * a mis-click waiting to happen — and the card face is for identifying the
 * deal, not for acting on it. `Nota Fiscal` is the terminal stage, so
 * archiving is still how a finished processo leaves the last column instead
 * of growing it without bound.
 */
import { Badge } from "@/components/ui/badge";
import { formatValor } from "../formatValor";
import { nomeDoProcesso, type ProcessoVenda } from "@/types/pipeline";

export interface ProcessoCardProps {
  processo: ProcessoVenda;
  isDragging?: boolean;
}

export function ProcessoCard({ processo, isDragging }: ProcessoCardProps) {
  const nome = nomeDoProcesso(processo);

  return (
    <div
      className={`cursor-pointer rounded-lg border bg-card p-3 shadow-sm transition-colors hover:border-primary/40 ${
        isDragging ? "opacity-60" : ""
      }`}
      data-testid="processo-card"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
          {nome.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{nome}</p>
          <p className="text-xs text-muted-foreground">
            {formatValor(Number(processo.valor || 0))}
          </p>
          {processo.arquivado && (
            <Badge variant="secondary" className="mt-1">
              Arquivado
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}
