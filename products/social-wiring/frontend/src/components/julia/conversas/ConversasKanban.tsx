/**
 * Kanban view of Conversas (`?view=kanban`) over the seed `KanbanBoard` organ:
 * fixed "Todas (n)" column with an eye toggle, one column per etiqueta,
 * "Adicionar coluna" → etiqueta picker, collapsed "Arquivadas" lane.
 * Dropping a card changes the contact's tags / archive flag.
 */
import { useEffect, useState } from "react";
import { Eye, EyeOff, Plus, ChevronRight, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { KanbanBoard } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import {
  mensagemErroConversas, useEtiquetas, useLaisConversas, usePatchContato,
  type Conversa, type FiltrosConversas,
} from "@/hooks/useLaisConversas";
import { EtiquetaPicker, SEM_ETIQUETA } from "./EtiquetaPicker";
import { COL_ARQUIVADAS, COL_TODAS, montarColunas, patchDoMovimento, type CartaoKanban } from "./kanbanColunas";

const LS_KEY = "lais:conversas:kanban-colunas";

function lerColunas(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(LS_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}

export function ConversasKanban({ filtros, onAbrir }: { filtros: FiltrosConversas; onAbrir: (c: Conversa) => void }) {
  const todas = useLaisConversas("todas", filtros);
  const arq = useLaisConversas("arquivadas", filtros);
  const { data: etiquetas = [] } = useEtiquetas();
  const patch = usePatchContato();
  const [colunas, setColunas] = useState<string[]>(lerColunas);
  const [todasVisivel, setTodasVisivel] = useState(true);
  const [arquivadasAberta, setArquivadasAberta] = useState(false);

  useEffect(() => { try { localStorage.setItem(LS_KEY, JSON.stringify(colunas)); } catch { /* storage unavailable */ } }, [colunas]);

  const showSkeleton = todas.isPending && !todas.data;
  const isRefreshing = todas.isFetching && !!todas.data;
  const listaTodas = todas.data ?? [];
  const listaArq = arq.data ?? [];

  const cols = montarColunas({ todas: listaTodas, arquivadas: listaArq, etiquetas, colunas, todasVisivel, arquivadasAberta });

  return (
    <div data-testid="conversas-kanban" data-refreshing={isRefreshing ? "true" : "false"}>
      <KanbanBoard<CartaoKanban>
        columns={cols}
        getCardId={(c) => c.key}
        getCardStage={(c) => c.stage}
        isLoading={showSkeleton}
        error={todas.isError && !todas.data ? new Error("Não foi possível carregar as conversas.") : undefined}
        emptyState={<p className="py-12 text-center text-sm text-muted-foreground">Nenhuma coluna.</p>}
        columnEmptyState={(s) => (s.id === COL_ARQUIVADAS && !arquivadasAberta ? null :
          <p className="py-4 text-center text-xs text-muted-foreground">Nenhuma conversa.</p>)}
        onCardActivate={(c) => onAbrir(c.conversa)}
        onMove={(key, de, para) => {
          const card = cols.flatMap((c) => c.cards).find((c) => c.key === key);
          const p = card ? patchDoMovimento(card.conversa, de, para) : null;
          if (!card || !p) return;
          patch.mutate({ id: card.conversa.contato_id, ...p }, {
            onError: (e) => toast.error(mensagemErroConversas(e, "Não foi possível mover a conversa.")),
          });
        }}
        renderCard={(c) => (
          <div className="space-y-1 text-sm" data-testid="kanban-card">
            <p className="truncate font-medium">{c.conversa.nome}</p>
            {c.conversa.ultima_mensagem && <p className="line-clamp-2 text-xs text-muted-foreground">{c.conversa.ultima_mensagem}</p>}
            <div className="flex flex-wrap gap-1">
              {(c.conversa.etiquetas ?? []).map((t) => (
                <span key={t.id} className="rounded-full bg-primary/10 px-1.5 text-[10px] text-primary">{t.nome}</span>
              ))}
            </div>
          </div>
        )}
        renderColumnHeader={(stage, cards) => {
          if (stage.id === COL_TODAS) {
            return (
              <div className="flex items-center justify-between px-1 py-1 text-sm font-semibold">
                <span>Todas ({listaTodas.length})</span>
                <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={todasVisivel ? "Ocultar conversas" : "Mostrar conversas"}
                  onClick={() => setTodasVisivel((v) => !v)} data-testid="kanban-todas-olho">
                  {todasVisivel ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                </Button>
              </div>
            );
          }
          if (stage.id === COL_ARQUIVADAS) {
            return (
              <button type="button" className="flex w-full items-center gap-1 px-1 py-1 text-sm font-semibold"
                onClick={() => setArquivadasAberta((v) => !v)} aria-expanded={arquivadasAberta} data-testid="kanban-arquivadas">
                {arquivadasAberta ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                Arquivadas ({listaArq.length})
              </button>
            );
          }
          return (
            <div className="flex items-center justify-between px-1 py-1 text-sm font-semibold">
              <span>{stage.label} ({cards.length})</span>
              <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={`Remover coluna ${stage.label}`}
                onClick={() => setColunas((cs) => cs.filter((x) => x !== stage.id))}>×</Button>
            </div>
          );
        }}
        renderTrailingColumn={() => (
          <div className="w-56 flex-shrink-0">
            <EtiquetaPicker comSemEtiqueta excluir={colunas}
              onSelect={(e) => setColunas((cs) => [...cs, typeof e === "string" ? SEM_ETIQUETA : e.id])}
              trigger={<Button variant="outline" size="sm" className="gap-1" data-testid="kanban-add-coluna"><Plus className="h-4 w-4" /> Adicionar coluna</Button>} />
          </div>
        )}
      />
    </div>
  );
}
