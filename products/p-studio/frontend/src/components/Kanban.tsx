import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { COR_STATUS, type TomStatus } from "@/lib/status";

export interface ColunaKanban {
  id: string;
  label: string;
}

/**
 * Kanban horizontal com arrastar-para-avançar. O protótipo tinha o layout
 * (rolagem lateral, contagem e total por coluna) mas era só leitura; aqui
 * soltar o cartão chama `onMover`, que bate na rota `/etapa` do backend.
 */
export function Kanban<T extends { id: string }>({
  colunas,
  itens,
  etapaDoItem,
  tomDaEtapa,
  totalDaColuna,
  renderCard,
  onMover,
  largura = "w-72",
}: {
  colunas: ColunaKanban[];
  itens: T[];
  etapaDoItem: (item: T) => string;
  tomDaEtapa: (etapa: string) => TomStatus;
  /** Rodapé opcional no cabeçalho da coluna (ex.: soma de valores). */
  totalDaColuna?: (itens: T[]) => ReactNode;
  renderCard: (item: T) => ReactNode;
  onMover?: (item: T, etapa: string) => void;
  largura?: string;
}) {
  const [arrastando, setArrastando] = useState<T | null>(null);
  const [alvo, setAlvo] = useState<string | null>(null);

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {colunas.map((coluna) => {
        const daColuna = itens.filter((i) => etapaDoItem(i) === coluna.id);
        return (
          <div key={coluna.id} className={cn("shrink-0", largura)}>
            <div className="mb-2 flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: COR_STATUS[tomDaEtapa(coluna.id)] }}
                />
                <span className="text-sm font-medium">{coluna.label}</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {daColuna.length}
                </span>
              </div>
              {totalDaColuna && (
                <span className="text-xs text-muted-foreground">{totalDaColuna(daColuna)}</span>
              )}
            </div>

            <div
              onDragOver={(e) => {
                if (!onMover || !arrastando) return;
                e.preventDefault();
                setAlvo(coluna.id);
              }}
              onDragLeave={() => setAlvo((a) => (a === coluna.id ? null : a))}
              onDrop={() => {
                setAlvo(null);
                if (!onMover || !arrastando) return;
                if (etapaDoItem(arrastando) !== coluna.id) onMover(arrastando, coluna.id);
                setArrastando(null);
              }}
              className={cn(
                "min-h-24 space-y-2 rounded-lg p-1 transition-colors",
                alvo === coluna.id && "bg-primary/5 ring-1 ring-primary/30"
              )}
            >
              {daColuna.map((item) => (
                <div
                  key={item.id}
                  draggable={!!onMover}
                  onDragStart={() => setArrastando(item)}
                  onDragEnd={() => {
                    setArrastando(null);
                    setAlvo(null);
                  }}
                  className={cn(onMover && "cursor-grab active:cursor-grabbing")}
                >
                  {renderCard(item)}
                </div>
              ))}
              {daColuna.length === 0 && (
                <p className="px-2 py-4 text-center text-xs text-muted-foreground/70">Vazio</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
