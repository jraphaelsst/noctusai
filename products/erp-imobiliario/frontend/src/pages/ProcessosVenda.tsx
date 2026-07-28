import { useState } from 'react';
import { useProcessos, useMoverProcessoEtapa, useArquivarProcesso } from '@/hooks/useProcessos';
import { ProcessoCard } from '@/components/processos/ProcessoCard';
import { ETAPAS_PROCESSO_CONFIG } from '@/lib/etapasProcessoConfig';
import { formatCurrency } from '@/lib/utils';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { KanbanBoard } from '@noctusai/lib/components';
import { Search } from 'lucide-react';

/**
 * Processos de Venda — the post-proposal execution board.
 *
 * Cards arrive here only via the Funil's "Aceitar Proposta" seam; there is no
 * create button, because a processo without the deal it came from has no
 * provenance. Built on the canonical `KanbanBoard` organ, same as the Funil.
 */
export default function ProcessosVenda() {
  const [busca, setBusca] = useState('');
  const [incluirArquivados, setIncluirArquivados] = useState(false);

  const { data: colunas, isPending, isFetching, error } = useProcessos({
    busca: busca || undefined,
    incluirArquivados,
  });
  const { mutate: moverProcesso } = useMoverProcessoEtapa();
  const { mutate: arquivarProcesso } = useArquivarProcesso();

  const totalProcessos = (colunas ?? []).reduce((sum, c) => sum + c.total, 0);
  const valorTotalGeral = (colunas ?? []).reduce((sum, c) => sum + c.valorTotal, 0);

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Processos de Venda</h1>
        <p className="text-sm text-muted-foreground">
          Execução pós-aceite da proposta — do contrato à nota fiscal.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Buscar por cliente ou negociação..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <Button
          variant={incluirArquivados ? 'default' : 'outline'}
          size="sm"
          onClick={() => setIncluirArquivados((v) => !v)}
        >
          {incluirArquivados ? 'Ocultar arquivados' : 'Mostrar arquivados'}
        </Button>
        {!isPending && !error && (
          <div className="text-sm text-muted-foreground ml-auto">
            <span className="font-medium text-foreground">{totalProcessos}</span> processo
            {totalProcessos === 1 ? '' : 's'} ·{' '}
            <span className="font-medium text-foreground">
              {formatCurrency(valorTotalGeral)}
            </span>
          </div>
        )}
      </div>

      <KanbanBoard
        // Gate on `isPending || isFetching`, never `isLoading` — during a
        // background refetch `isLoading` is false, which would render the
        // empty board over data that exists.
        isLoading={isPending || isFetching}
        error={error}
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="w-80 h-96 flex-shrink-0" />
            ))}
          </div>
        }
        columns={(colunas ?? []).map((coluna) => ({
          stage: { id: coluna.etapa, label: ETAPAS_PROCESSO_CONFIG[coluna.etapa].label },
          cards: coluna.cards,
        }))}
        getCardId={(processo) => processo.id}
        getCardStage={(processo) => processo.etapa}
        renderCard={(processo, { isDragging }) => (
          <ProcessoCard
            processo={processo}
            isDragging={isDragging}
            onArquivar={arquivarProcesso}
          />
        )}
        renderColumnHeader={(stage, cards) => {
          const config = ETAPAS_PROCESSO_CONFIG[stage.id];
          const valorTotal = cards.reduce((sum, c) => sum + Number(c.valor || 0), 0);
          return (
            <div className={`p-4 border-b ${config.bgColor} ${config.borderColor}`}>
              <div className="flex items-center justify-between mb-2 gap-2">
                <h3 className={`font-semibold text-sm ${config.color} min-w-0 truncate`}>
                  {config.label}
                </h3>
                <Badge variant="secondary">{cards.length}</Badge>
              </div>
              <p className="text-sm font-medium">{formatCurrency(valorTotal)}</p>
            </div>
          );
        }}
        columnEmptyState={() => (
          <div className="text-center text-muted-foreground text-sm py-8">
            Nenhum processo nesta etapa
          </div>
        )}
        onMove={(cardId, fromStage, toStage, toIndex) => {
          if (fromStage === toStage) return;
          moverProcesso({
            processo_id: cardId,
            para_etapa: toStage,
            novo_indice: toIndex,
          });
        }}
        columnClassName="flex-shrink-0 w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden [&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto"
      />
    </div>
  );
}
