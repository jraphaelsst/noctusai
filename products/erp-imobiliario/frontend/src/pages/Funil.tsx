import { useState } from 'react';
import { FiltrosFunil } from '@/components/clientes/FiltrosFunil';
import { NovoClienteDialog } from '@/components/clientes/NovoClienteDialog';
import { useFunil, useMoverClienteEtapa } from '@/hooks/useFunil';
import { useToggleArquivarCliente } from '@/hooks/useClientes';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { ClienteCard } from '@/components/clientes/ClienteCard';
import { ETAPAS_CONFIG } from '@/lib/etapasConfig';
import { formatCurrency } from '@/lib/utils';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { KanbanBoard } from '@noctusai/lib/components';

export default function Funil() {
  const [novoClienteOpen, setNovoClienteOpen] = useState(false);
  const [atividadeClienteId, setAtividadeClienteId] = useState<string | null>(null);

  const filtrosStore = useFunilFiltrosStore();
  const { data: colunas, isLoading } = useFunil({
    ...filtrosStore,
    etapa: filtrosStore.etapa === 'todas' ? undefined : filtrosStore.etapa,
  });
  const { mutate: moverCliente } = useMoverClienteEtapa();
  const { mutate: toggleArquivar } = useToggleArquivarCliente();

  if (isLoading) {
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
        getCardId={(cliente) => cliente.id}
        getCardStage={(cliente) => cliente.etapa_atual}
        renderCard={(cliente, { isDragging }) => (
          <ClienteCard
            cliente={cliente}
            isDragging={isDragging}
            onRegistrarAtividade={setAtividadeClienteId}
            onArquivar={toggleArquivar}
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
            Nenhum cliente nesta etapa
          </div>
        )}
        onMove={(cardId, fromStage, toStage, toIndex) => {
          // Mirrors the pre-organ behavior: only cross-stage drops mutate.
          // Reordering within the same column is a client-side no-op.
          if (fromStage === toStage) return;
          moverCliente({ cliente_id: cardId, para_etapa: toStage, novo_indice: toIndex });
        }}
        columnClassName="flex-shrink-0 w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden [&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto"
      />

      <NovoClienteDialog open={novoClienteOpen} onOpenChange={setNovoClienteOpen} />
    </div>
  );
}
