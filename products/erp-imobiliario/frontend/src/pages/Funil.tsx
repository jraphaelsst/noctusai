import { useState } from 'react';
import { PipelineBoard } from '@noctusai/lib/components';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';

import { FiltrosFunil } from '@/components/clientes/FiltrosFunil';
import { NovoClienteDialog } from '@/components/clientes/NovoClienteDialog';
import { NegociacaoCard } from '@/components/clientes/NegociacaoCard';
import { useAceitarProposta, useArquivarNegociacao } from '@/hooks/useFunil';
import { funilPipeline } from '@/lib/pipelines';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { formatCurrency } from '@/lib/utils';

/**
 * Funil de Vendas — the pre-proposal negotiation board.
 *
 * Cards are NEGOCIAÇÕES (a cliente can hold several concurrent deals), and
 * stages are per-organization DB rows the user edits via "Configurar etapas".
 * The board reflects a rename or reorder on the next refresh, with no deploy.
 */
export default function Funil() {
  const [novoClienteOpen, setNovoClienteOpen] = useState(false);
  const [, setAtividadeClienteId] = useState<string | null>(null);

  const filtrosStore = useFunilFiltrosStore();
  const { mutate: aceitarProposta, isPending: aceitando } = useAceitarProposta();
  const { mutate: arquivarNegociacao } = useArquivarNegociacao();

  // Pass ONLY the filter fields. Spreading the whole store also hands over its
  // setter functions, which the filter type does not describe.
  const filtros = {
    busca: filtrosStore.busca,
    responsavel_id: filtrosStore.responsavelId,
    origem: filtrosStore.origem,
    incluir_arquivados: filtrosStore.incluirArquivados,
    data_inicio: filtrosStore.dataInicio,
    data_fim: filtrosStore.dataFim,
    etapa_id: filtrosStore.etapa === 'todas' ? undefined : filtrosStore.etapa,
  };

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <FiltrosFunil onNovoCliente={() => setNovoClienteOpen(true)} />

      <PipelineBoard
        hooks={funilPipeline}
        filtros={filtros}
        formatValue={formatCurrency}
        emptyColumnLabel="Nenhuma negociação nesta etapa"
        // Previously this page returned a full-page skeleton from
        // `if (isPending || isFetching)`, which blanked the FILTER BAR on every
        // background refetch — so changing a filter made the controls vanish
        // under the user mid-interaction. Scoping the loading state to the
        // board keeps the filters mounted and interactive throughout.
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="w-80 h-96 flex-shrink-0" />
            ))}
          </div>
        }
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
      />

      <NovoClienteDialog open={novoClienteOpen} onOpenChange={setNovoClienteOpen} />
    </div>
  );
}
