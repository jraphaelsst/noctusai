import { useState } from 'react';
import { PipelineBoard } from '@noctusai/lib/components';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { Search } from 'lucide-react';

import { ProcessoCard } from '@/components/processos/ProcessoCard';
import { processosPipeline } from '@/lib/pipelines';
import { useArquivarProcesso } from '@/hooks/useProcessos';
import { formatCurrency } from '@/lib/utils';

/**
 * Processos de Venda — the post-proposal execution board.
 *
 * Cards arrive here only via the Funil's "Aceitar Proposta" seam; there is no
 * create button, because a processo without the deal it came from has no
 * provenance.
 *
 * Stages are DB rows the user edits ("Configurar etapas" on the board), so this
 * page no longer knows how many columns exist or what they are called — it used
 * to hardcode 8 via `ETAPAS_PROCESSO_CONFIG`.
 */
export default function ProcessosVenda() {
  const [busca, setBusca] = useState('');
  const [incluirArquivados, setIncluirArquivados] = useState(false);

  const { mutate: arquivarProcesso } = useArquivarProcesso();

  const filtros = {
    busca: busca || undefined,
    incluir_arquivados: incluirArquivados,
  };

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Processos de Venda</h1>
        <p className="text-sm text-muted-foreground">
          Execução pós-aceite da proposta — do contrato à nota fiscal.
        </p>
      </div>

      <PipelineBoard
        hooks={processosPipeline}
        filtros={filtros}
        formatValue={formatCurrency}
        emptyColumnLabel="Nenhum processo nesta etapa"
        toolbar={
          <>
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
          </>
        }
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="w-80 h-96 flex-shrink-0" />
            ))}
          </div>
        }
        renderCard={(processo, { isDragging }) => (
          <ProcessoCard
            processo={processo}
            isDragging={isDragging}
            onArquivar={arquivarProcesso}
          />
        )}
      />
    </div>
  );
}
