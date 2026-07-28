import { useState } from 'react';
import { FiltrosFunil } from '@/components/clientes/FiltrosFunil';
import { NovoClienteDialog } from '@/components/clientes/NovoClienteDialog';
import {
  useFunil,
  useMoverNegociacaoEtapa,
  useAceitarProposta,
  useArquivarNegociacao,
} from '@/hooks/useFunil';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { NegociacaoCard } from '@/components/clientes/NegociacaoCard';
import { ETAPAS_CONFIG } from '@/lib/etapasConfig';
import { formatCurrency } from '@/lib/utils';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { KanbanBoard } from '@noctusai/lib/components';

export default function Funil() {
  const [novoClienteOpen, setNovoClienteOpen] = useState(false);
  const [atividadeClienteId, setAtividadeClienteId] = useState<string | null>(null);

  const filtrosStore = useFunilFiltrosStore();
  // Pass ONLY the filter fields. Spreading the whole store also hands over its
  // setter functions, which the filter type does not describe — an excess-
  // property error that went unseen while `tsc --noEmit` checked zero files.
  const { data: colunas, isPending, isFetching } = useFunil({
    busca: filtrosStore.busca,
    responsavelId: filtrosStore.responsavelId,
    origem: filtrosStore.origem,
    incluirArquivados: filtrosStore.incluirArquivados,
    dataInicio: filtrosStore.dataInicio,
    dataFim: filtrosStore.dataFim,
    etapa: filtrosStore.etapa === 'todas' ? undefined : filtrosStore.etapa,
  });
  const { mutate: moverNegociacao } = useMoverNegociacaoEtapa();
  const { mutate: aceitarProposta, isPending: aceitando } = useAceitarProposta();
  const { mutate: arquivarNegociacao } = useArquivarNegociacao();

  // Gate on `isPending || isFetching`, never `isLoading`: TanStack v5's
  // `isLoading` is false during a background refetch, so a filter change would
  // flash the skeleton logic over data that already exists.
  if (isPending || isFetching) {
    return (
      <div className="container mx-auto p-4 sm:p-6">
        <Skeleton className="h-12 w-64 mb-6" />
        <div className="flex gap-4 overflow-x-auto pb-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="w-80 h-96 flex-shrink-0" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <FiltrosFunil onNovoCliente={() => setNovoClienteOpen(true)} />

      <KanbanBoard
        columns={(colunas ?? []).map((coluna) => ({
          stage: { id: coluna.etapa, label: ETAPAS_CONFIG[coluna.etapa].label },
          cards: coluna.cards,
        }))}
        getCardId={(negociacao) => negociacao.id}
        getCardStage={(negociacao) => negociacao.etapa}
        renderCard={(negociacao, { isDragging }) => (
          <NegociacaoCard
            negociacao={negociacao}
            isDragging={isDragging}
            onRegistrarAtividade={setAtividadeClienteId}
            onArquivar={arquivarNegociacao}
            onAceitarProposta={aceitarProposta}
            aceitandoProposta={aceitando}
          />
        )}
        renderColumnHeader={(stage, cards) => {
          const config = ETAPAS_CONFIG[stage.id];
          const valorTotal = cards.reduce((sum, c) => sum + Number(c.valor_estimado || 0), 0);
          return (
            <div className={`p-4 border-b ${config.bgColor} ${config.borderColor}`}>
              <div className="flex items-center justify-between mb-2">
                <h3 className={`font-semibold ${config.color}`}>{config.label}</h3>
                <Badge variant="secondary">{cards.length}</Badge>
              </div>
              <p className="text-sm font-medium">{formatCurrency(valorTotal)}</p>
            </div>
          );
        }}
        columnEmptyState={() => (
          <div className="text-center text-muted-foreground text-sm py-8">
            Nenhuma negociação nesta etapa
          </div>
        )}
        onMove={(cardId, fromStage, toStage, toIndex) => {
          // Mirrors the pre-organ behavior: only cross-stage drops mutate.
          // Reordering within the same column is a client-side no-op.
          if (fromStage === toStage) return;
          moverNegociacao({
            negociacao_id: cardId,
            para_etapa: toStage,
            novo_indice: toIndex,
          });
        }}
        columnClassName="flex-shrink-0 w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden [&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto"
      />

      <NovoClienteDialog open={novoClienteOpen} onOpenChange={setNovoClienteOpen} />
    </div>
  );
}
