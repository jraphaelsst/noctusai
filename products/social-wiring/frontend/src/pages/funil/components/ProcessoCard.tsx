/**
 * A Processos de Venda card — one accepted deal in delivery.
 *
 * `Faturamento` is the terminal stage, so archiving is how a finished processo
 * leaves the last column instead of growing it without bound.
 */
import { Archive, ArchiveRestore } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatValor } from "../formatValor";
import type { ProcessoVenda } from "@/types/pipeline";

export interface ProcessoCardProps {
  processo: ProcessoVenda;
  isDragging?: boolean;
  onArquivar?: (processoId: string) => void;
}

export function ProcessoCard({ processo, isDragging, onArquivar }: ProcessoCardProps) {
  const nome = processo.negociacao?.titulo || "Processo";

  return (
    <div
      className={`rounded-lg border bg-card p-3 shadow-sm ${isDragging ? "opacity-60" : ""}`}
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

      {onArquivar && (
        <div className="mt-3 flex gap-1 border-t pt-2">
          <Button
            variant="ghost"
            size="sm"
            title={processo.arquivado ? "Restaurar processo" : "Arquivar processo"}
            onClick={(e) => {
              // The card body carries dnd-kit's drag listeners.
              e.stopPropagation();
              onArquivar(processo.id);
            }}
          >
            {processo.arquivado ? (
              <ArchiveRestore className="h-4 w-4" />
            ) : (
              <Archive className="h-4 w-4" />
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
