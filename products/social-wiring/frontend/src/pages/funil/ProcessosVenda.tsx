/**
 * Processos de Venda — post-acceptance delivery at `/processos-venda`.
 *
 * Cards arrive here only through the Funil's "Aceitar Proposta" seam; there is
 * no create button, because a processo without the deal it came from has no
 * provenance.
 *
 * Stages are DB rows the user edits ("Configurar etapas"). Since migration
 * 037 the defaults are erp-imobiliario's, verbatim (Elaboração do Contrato →
 * Análise das Partes → Revisão do Contrato → Assinatura → Financiamento &
 * Escritura → Finalização → Entrega das Chaves → Nota Fiscal): the two
 * products serve the same business, and two boards with different column
 * names for the same deal is a reporting problem and a training problem.
 */
import { useState } from "react";
import { Archive, ArchiveRestore, Search } from "lucide-react";

import { PipelineBoard } from "@noctusai/lib/components";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LeadDetailModal } from "@/components/LeadDetailModal";
import { useArquivarProcesso } from "@/hooks/useProcessosVenda";
import { formatValor } from "./formatValor";
import { processosPipeline } from "@/lib/pipelines";
import { ProcessoCard } from "./components/ProcessoCard";
import { origemDoProcesso, type ProcessoVenda } from "@/types/pipeline";

export default function ProcessosVenda() {
  const [busca, setBusca] = useState("");
  const [incluirArquivados, setIncluirArquivados] = useState(false);
  // The whole processo, not just its origin: unlike the Funil, this modal
  // also offers "Arquivar", which needs the processo's own id and its
  // current `arquivado` state to label the button.
  const [detalhe, setDetalhe] = useState<ProcessoVenda | null>(null);
  const { mutate: arquivarProcesso } = useArquivarProcesso();

  const origem = detalhe ? origemDoProcesso(detalhe) : null;

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="mb-1 text-2xl font-bold">Processos de Venda</h1>
        <p className="text-sm text-muted-foreground">
          Execução pós-aceite da proposta — do contrato ao faturamento.
        </p>
      </div>

      <PipelineBoard
        hooks={processosPipeline}
        filtros={{ busca: busca || undefined, incluir_arquivados: incluirArquivados }}
        formatValue={formatValor}
        emptyColumnLabel="Nenhum processo nesta etapa"
        toolbar={
          <>
            <div className="relative min-w-[240px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Buscar por negociação ou observações..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
              />
            </div>
            <Button
              variant={incluirArquivados ? "default" : "outline"}
              size="sm"
              onClick={() => setIncluirArquivados((v) => !v)}
            >
              {incluirArquivados ? "Ocultar arquivados" : "Mostrar arquivados"}
            </Button>
          </>
        }
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-96 w-80 flex-shrink-0" />
            ))}
          </div>
        }
        // Wrapped, not passed as `setDetalhe` directly: a bare setter reads a
        // ProcessoVenda as a SetStateAction updater function.
        onCardClick={(processo) => setDetalhe(processo)}
        renderCard={(processo, { isDragging }) => (
          <ProcessoCard processo={processo} isDragging={isDragging} />
        )}
      />

      {/*
        The same modal the Leads table and the Funil board open — plus the
        archive action, which moved off the card face to here.
      */}
      <LeadDetailModal
        open={!!detalhe}
        onClose={() => setDetalhe(null)}
        leadId={origem?.leadId ?? null}
        campanha={origem?.campanha ?? null}
        actions={
          detalhe
            ? [
                {
                  label: detalhe.arquivado ? "Restaurar processo" : "Arquivar processo",
                  variant: "outline",
                  align: "start",
                  icon: detalhe.arquivado ? (
                    <ArchiveRestore className="mr-1 h-4 w-4" />
                  ) : (
                    <Archive className="mr-1 h-4 w-4" />
                  ),
                  onClick: () => {
                    arquivarProcesso(detalhe.id);
                    setDetalhe(null);
                  },
                },
              ]
            : []
        }
      />
    </div>
  );
}
